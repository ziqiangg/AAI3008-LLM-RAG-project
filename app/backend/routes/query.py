"""
Query/RAG routes - Full RAG pipeline implementation
Handles question answering with retrieval, reranking, and generation
"""
import logging
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from datetime import datetime

from app.backend.database import get_db_session
from app.backend.models import Session as ConvSession, Message
from app.backend.services.injestion import get_embeddings
from app.backend.services import retrieval, reranking, generation, classification,web_retrieval
from app.backend.config import Config
from app.backend.services.tool_detection import detect_and_generate_tool

import os
print(">>> LOADED query.py from:", os.path.abspath(__file__), flush=True)
# Language support: detect_language for identifying query language
from app.backend.services.translation import detect_language

query_bp = Blueprint('query', __name__)
logger = logging.getLogger(__name__)


@query_bp.route('', methods=['POST'])
def ask_question():
    """
    Ask a question and get AI-generated answer based on uploaded documents.

    RAG Pipeline (vector-first, web-secondary):
    1. Validate input and retrieve session/conversation history
    2. Embed the question using HuggingFace embeddings
    3. Retrieve top K relevant chunks via vector similarity search (PRIMARY)
    4. Rerank vector chunks using cross-encoder (PRIMARY)
    5. (Optional) Web retrieval + rerank (SECONDARY LANE; appended after docs)
    6. Generate answer using Gemini API with context (docs first, then web)
    7. Store messages in database
    8. Return answer with source citations

    Expected JSON payload:
    {
        "question": str (required),
        "session_id": int (optional),
        "document_ids": [int] (optional),
        "web_search": bool (optional)   # NEW: UI toggle
    }
    """
    try:
        # ═══════════════════════════════════════════════════════════
        # 1. VALIDATE INPUT & CHECK AUTHENTICATION
        # ═══════════════════════════════════════════════════════════
        data = request.get_json()

        if not data or 'question' not in data:
            return jsonify({'error': 'question is required'}), 400

        question = data['question'].strip()
        if not question:
            return jsonify({'error': 'question cannot be empty'}), 400
        logger.warning(f"[DEBUG] Payload web_search={data.get('web_search')} question='{question[:60]}'")
        session_id = data.get('session_id')
        document_ids = data.get('document_ids')

        # NEW: web toggle + explicit ask detection (only triggers web lane)
        web_toggle = bool(data.get('web_search', False))
        web_explicit = web_retrieval.user_explicitly_requested_web(question)
        web_enabled = web_toggle or web_explicit
        diagram_enabled = bool(data.get('diagram', False))

        # Check if user is authenticated (optional)
        current_user_id = None
        try:
            verify_jwt_in_request(optional=True)
            current_user_id = get_jwt_identity()
            if current_user_id:
                current_user_id = int(current_user_id)
        except Exception:
            pass  # Not authenticated, that's okay

        with get_db_session() as db:
            conversation_history = []
            # ═══════════════════════════════════════════════════════════
            # DETECT LANGUAGE (For multilingual support)
            # ═══════════════════════════════════════════════════════════
            lang_info = detect_language(question)
            detected_lang_code = lang_info['code']
            detected_lang_name = lang_info['name']
            logger.info(f"[Query] Detected language: {detected_lang_code} ({detected_lang_name})")
            
            # ═══════════════════════════════════════════════════════════
            # 2. RETRIEVE SESSION & CONVERSATION HISTORY
            # ═══════════════════════════════════════════════════════════
            session = None
            if session_id:
                session = db.query(ConvSession).filter_by(id=session_id).first()

                if not session:
                    return jsonify({'error': f'Session {session_id} not found'}), 404

                # Verify session ownership if user is authenticated
                if current_user_id and session.user_id != current_user_id:
                    return jsonify({'error': 'Access denied to this session'}), 403

                # Get conversation history (last N messages)
                messages = (
                    db.query(Message)
                    .filter_by(session_id=session_id)
                    .order_by(Message.created_at.desc())
                    .limit(Config.MAX_CONVERSATION_HISTORY)
                    .all()
                )

                # Reverse to chronological order
                messages.reverse()
                conversation_history = [
                    {'role': msg.role, 'content': msg.content}
                    for msg in messages
                ]

                # Update session last accessed
                session.last_accessed = datetime.utcnow()

                # Use session's document_ids if not provided in request
                if not document_ids and session.document_ids:
                    document_ids = session.document_ids

            logger.info(f"[Query] Question: '{question[:50]}...'")
            logger.info(f"[Query] Session: {session_id}, Documents: {document_ids}, History: {len(conversation_history)} msgs")
            logger.info(f"[Query] Web enabled: {web_enabled} (toggle={web_toggle}, explicit={web_explicit})")

            # ═══════════════════════════════════════════════════════════
            # 3. EMBED QUESTION (No translation needed - multilingual model handles cross-lingual semantic matching)
            # ═══════════════════════════════════════════════════════════
            # Using multilingual embedding model that supports Chinese, English, and 50+ languages
            # Cross-lingual retrieval works automatically (e.g., Chinese query → English documents)
            embeddings_model = get_embeddings()
            question_embedding = embeddings_model.embed_query(question)  # Use original language
            logger.info(f"[Query] Question embedded ({detected_lang_name}): {len(question_embedding)} dimensions")

            # ═══════════════════════════════════════════════════════════
            # 4. VECTOR RETRIEVAL (PRIMARY)
            # ═══════════════════════════════════════════════════════════
            retrieved_chunks = retrieval.retrieve_relevant_chunks(
                db_session=db,
                question_embedding=question_embedding,
                document_ids=document_ids,
                top_k=Config.TOP_K_RETRIEVAL
            )

            if not retrieved_chunks:
                return jsonify({
                    'answer': (
                        "I couldn't find any relevant information in the uploaded documents to answer your question. "
                        "Please ensure you have uploaded documents or try rephrasing your question."
                    ),
                    'sources': [],
                    'session_id': session_id,
                    'metadata': {
                        'num_chunks_retrieved': 0,
                        'num_chunks_reranked': 0,
                        'num_web_chunks': 0,
                        'error': 'No relevant chunks found'
                    }
                }), 200

            logger.info(f"[Query] Retrieved {len(retrieved_chunks)} chunks (docs)")

            # ═══════════════════════════════════════════════════════════
            # 5. OPTIONAL WEB RETRIEVAL (SECONDARY LANE)
            #     Language-aware: searches language-appropriate sources
            # ═══════════════════════════════════════════════════════════
            web_chunks = []
            if web_enabled:
                try:
                    # Pass language code for language-aware web search and domain filtering
                    web_chunks = web_retrieval.web_retrieve_as_chunks(question, lang_code=detected_lang_code)
                    logger.info(f"[Query] Retrieved {len(web_chunks)} chunks (web, lang={detected_lang_code})")
                except Exception as e:
                    logger.warning(f"[Query] Web retrieval failed, skipping web sources: {e}")
                    web_chunks = []

            # ═══════════════════════════════════════════════════════════
            # 6. UNIFIED RERANKING (DOCS + WEB COMBINED)
            #     All chunks ranked together - best sources win regardless of type
            # ═══════════════════════════════════════════════════════════
            all_chunks = retrieved_chunks + web_chunks
            logger.info(f"[Query] Combined pool: {len(retrieved_chunks)} docs + {len(web_chunks)} web = {len(all_chunks)} total")

            try:
                final_context_chunks = reranking.rerank_chunks(
                    question=question,
                    chunks=all_chunks,
                    top_k=Config.RERANK_TOP_K
                )
                logger.info(f"[Query] Unified reranking: top {len(final_context_chunks)} chunks selected")
                # Log source type breakdown
                doc_count = sum(1 for c in final_context_chunks if c.get('metadata', {}).get('source_type') != 'web')
                web_count = len(final_context_chunks) - doc_count
                logger.info(f"[Query] Final mix: {doc_count} docs + {web_count} web")
            except Exception as e:
                logger.warning(f"[Query] Unified reranking failed, using top retrieval results: {e}")
                final_context_chunks = all_chunks[:Config.RERANK_TOP_K]

            
            # ═══════════════════════════════════════════════════════════
            # 6. SUBJECT CLASSIFICATION
            # ═══════════════════════════════════════════════════════════
            subject_context = classification.extract_subject_context(final_context_chunks)
            logger.info(
                f"[Query] Subject context: {subject_context['dominant_subject']} "
                f"(confidence: {subject_context['dominant_confidence']:.2f})"
            )

            # ═══════════════════════════════════════════════════════════
            # LANGUAGE INSTRUCTION FOR GEMINI PROMPT
            # ═══════════════════════════════════════════════════════════
            language_info = {
                'code': detected_lang_code,
                'name': detected_lang_name,
                'is_english': detected_lang_code == 'en'
            }

            # ═══════════════════════════════════════════════════════════
            # GENERATE ANSWER IN USER'S LANGUAGE
            # ═══════════════════════════════════════════════════════════
            result = generation.generate_answer(
                question=question,
                context_chunks=final_context_chunks,
                conversation_history=conversation_history,
                subject_context=subject_context,
                language_info=language_info,
                web_enabled=web_enabled
            )

            answer = result['answer']
            try:
                tool_output = detect_and_generate_tool(
                    question=question,
                    context_chunks=final_context_chunks
                )
                logger.warning(f"[Tool] output type: {tool_output['type'] if tool_output else 'none'}")
            except Exception as tool_err:
                logger.warning(f"[Tool] Detection failed: {tool_err}")
                tool_output = None

            # ═══════════════════════════════════════════════════════════
            # 7. PREPARE SOURCE CITATIONS (docs + web)
            # ═══════════════════════════════════════════════════════════
            sources = []
            for i, chunk in enumerate(final_context_chunks, 1):
                md = chunk.get('metadata', {}) or {}
                sources.append({
                    "chunk_id": chunk.get("chunk_id"),
                    "doc_id": chunk.get("document_id"),  # Changed from document_id to doc_id for frontend compatibility
                    "filename": chunk.get("filename"),
                    "content": chunk.get("content", "")[:300] + ("..." if len(chunk.get("content","")) > 300 else ""),
                    "score": chunk.get("rerank_score", chunk.get("similarity", 0.0)),
                    "chunk_order": chunk.get("chunk_order", 0),
                    "citation_index": i,  # Preserve LLM's reference order (S1, S2, etc.) even after frontend sorting
                    "metadata": md,
                    "source_type": md.get("source_type", "doc"),     # "doc" or "web"
                    "url": md.get("url"),                           # only for web
                    "title": md.get("title"),                       # only for web
                })

            # ═══════════════════════════════════════════════════════════
            # 8. STORE MESSAGES IN DATABASE (if session exists)
            # ═══════════════════════════════════════════════════════════
            if session_id:
                user_msg = Message(
                    session_id=session_id,
                    role='user',
                    content=question
                )
                db.add(user_msg)

                assistant_msg = Message(
                    session_id=session_id,
                    role='assistant',
                    content=answer,
                    sources={'chunks': sources}
                )
                db.add(assistant_msg)

                # Auto-generate session title from first question only
                if session and session.title == 'New Chat':
                    message_count = db.query(Message).filter_by(session_id=session_id).count()
                    if message_count == 0:
                        session.title = question[:60] + ('...' if len(question) > 60 else '')

                db.commit()
                logger.info(f"[Query] Messages stored in session {session_id}")

            # ═══════════════════════════════════════════════════════════
            # 9. RETURN RESPONSE
            # ═══════════════════════════════════════════════════════════
            # Calculate source type breakdown for metadata
            num_doc_chunks = sum(1 for c in final_context_chunks if c.get('metadata', {}).get('source_type') != 'web')
            num_web_chunks = len(final_context_chunks) - num_doc_chunks
            
            return jsonify({
                'answer': answer,
                'sources': sources,
                'tool': tool_output,
                'session_id': session_id,
                'detected_language': {
                    'code': detected_lang_code,
                    'name': detected_lang_name
                },
                'metadata': {
                    'model': result['model_used'],
                    'num_chunks_retrieved': len(retrieved_chunks),
                    'num_chunks_reranked': len(final_context_chunks),
                    'num_doc_chunks': num_doc_chunks,
                    'num_web_chunks': num_web_chunks,
                    'num_context_messages': len(conversation_history),
                    'finish_reason': result.get('finish_reason', 'COMPLETED'),
                    'web_enabled': web_enabled
                }
            }), 200

    except Exception as e:
        logger.error(f"[Query] Pipeline error: {e}", exc_info=True)
        return jsonify({
            'error': 'An error occurred while processing your question',
            'details': str(e) if current_app.debug else 'Enable debug mode for details'
        }), 500