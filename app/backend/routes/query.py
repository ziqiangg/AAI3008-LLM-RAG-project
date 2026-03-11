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
from app.backend.services.query_rewriter import get_query_rewriter
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
        folder_ids = data.get('folder_ids')  # NEW: filter by folders

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

            # ═══════════════════════════════════════════════════════════
            # 2b. RESOLVE FOLDER IDS TO DOCUMENT IDS
            # ═══════════════════════════════════════════════════════════
            if folder_ids and len(folder_ids) > 0:
                from app.backend.models import Document as DocModel
                folder_doc_rows = (
                    db.query(DocModel.id)
                    .filter(DocModel.folder_id.in_(folder_ids))
                    .all()
                )
                folder_doc_ids = [r.id for r in folder_doc_rows]
                if document_ids:
                    # Intersect: only docs that are both in the specified doc list AND the folders
                    document_ids = list(set(document_ids) & set(folder_doc_ids))
                else:
                    document_ids = folder_doc_ids
                logger.info(f"[Query] Folder filter applied: folder_ids={folder_ids} → {len(document_ids)} docs")

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
            # 6a. ADAPTIVE QUERY REWRITING (Phase 1 & 2)
            #     Triggered when relevance scores are low or conversational context needed
            # ═══════════════════════════════════════════════════════════
            # Initialize rewriting tracking variables (always set to avoid UnboundLocalError)
            original_question = question  # Preserve original for logging
            query_was_rewritten = False
            rewrite_strategy_used = None
            original_avg_score = 0.0
            rewritten_avg_score = 0.0
            
            logger.warning(f"[QueryRewrite] Config.QUERY_REWRITE_ENABLED = {Config.QUERY_REWRITE_ENABLED}")
            
            if Config.QUERY_REWRITE_ENABLED and final_context_chunks:
                # Calculate average rerank score to assess retrieval quality
                avg_rerank_score = (
                    sum(c.get('rerank_score', 0) for c in final_context_chunks) / len(final_context_chunks)
                    if final_context_chunks else 0.0
                )
                logger.warning(f"[QueryRewrite] Feature enabled, checking scores...")
                logger.warning(f"[QueryRewrite] Average rerank score: {avg_rerank_score:.2f}")
                logger.warning(f"[QueryRewrite] Thresholds - Poor: {Config.RERANK_QUALITY_THRESHOLD_POOR}, Decent: {Config.RERANK_QUALITY_THRESHOLD_DECENT}")
                logger.warning(f"[QueryRewrite] Conversation history messages: {len(conversation_history) if conversation_history else 0}")
                
                # Determine if query rewriting is needed
                needs_rewrite = False
                rewrite_reason = ""
                
                if avg_rerank_score < Config.RERANK_QUALITY_THRESHOLD_POOR:
                    # Critical: Very low scores, definitely rewrite
                    needs_rewrite = True
                    rewrite_reason = f"low relevance (avg={avg_rerank_score:.2f} < {Config.RERANK_QUALITY_THRESHOLD_POOR})"
                    logger.warning(f"[QueryRewrite] {rewrite_reason}")
                    
                elif avg_rerank_score < Config.RERANK_QUALITY_THRESHOLD_DECENT:
                    # Moderate scores: Check if conversational context could help
                    if conversation_history and len(conversation_history) >= 2:
                        needs_rewrite = True
                        rewrite_reason = f"moderate relevance with conversation (avg={avg_rerank_score:.2f} < {Config.RERANK_QUALITY_THRESHOLD_DECENT})"
                        logger.info(f"[QueryRewrite] {rewrite_reason}")
                
                if needs_rewrite:
                    try:
                        query_rewriter = get_query_rewriter()
                        
                        # Select rewriting strategy
                        if Config.QUERY_REWRITE_STRATEGY_AUTO:
                            strategy = query_rewriter.analyze_query_needs(
                                query=question,
                                conversation_history=conversation_history,
                                avg_rerank_score=avg_rerank_score
                            )
                            logger.warning(f"[QueryRewrite] Auto-selected strategy: {strategy}")
                        else:
                            # Default to conversation context fusion
                            strategy = 'conversation_context'
                        
                        # Apply rewriting strategy
                        rewritten_query = None
                        
                        if strategy == 'conversation_context':
                            rewritten_query = query_rewriter.rewrite_with_conversation_context(
                                current_query=question,
                                conversation_history=conversation_history
                            )
                        elif strategy == 'expansion':
                            variants = query_rewriter.expand_query_with_synonyms(
                                original_query=question,
                                num_variants=Config.QUERY_REWRITE_MAX_VARIANTS
                            )
                            # For now, use first variant (future: multi-variant retrieval)
                            rewritten_query = variants[0] if variants else question
                        elif strategy == 'decomposition':
                            sub_questions = query_rewriter.decompose_complex_query(question)
                            # For now, use first sub-question (future: multi-query retrieval)
                            rewritten_query = sub_questions[0] if sub_questions else question
                        elif strategy == 'hyde':
                            hypothetical_doc = query_rewriter.generate_hypothetical_document(question)
                            # Embed the hypothetical document instead of query
                            rewritten_query = hypothetical_doc
                        else:
                            rewritten_query = question
                        
                        # If query was actually rewritten, retry retrieval
                        if rewritten_query and rewritten_query != question:
                            logger.warning(f"[QueryRewrite] Retrying retrieval with rewritten query")
                            logger.warning(f"  Original: {question}")
                            logger.warning(f"  Rewritten: {rewritten_query[:200]}..." if len(rewritten_query) > 200 else f"  Rewritten: {rewritten_query}")
                            
                            # Re-embed rewritten query
                            embeddings_model = get_embeddings()
                            rewritten_embedding = embeddings_model.embed_query(rewritten_query)
                            
                            # Re-retrieve with rewritten query
                            retry_chunks = retrieval.retrieve_relevant_chunks(
                                db_session=db,
                                question_embedding=rewritten_embedding,
                                document_ids=document_ids,
                                top_k=Config.TOP_K_RETRIEVAL
                            )
                            
                            # Re-rank with rewritten query
                            retry_final = reranking.rerank_chunks(
                                question=rewritten_query,
                                chunks=retry_chunks + web_chunks,  # Include web chunks in reranking
                                top_k=Config.RERANK_TOP_K
                            )
                            
                            # Calculate new average score
                            retry_avg_score = (
                                sum(c.get('rerank_score', 0) for c in retry_final) / len(retry_final)
                                if retry_final else 0.0
                            )
                            
                            # Store scores for metadata tracking
                            original_avg_score = avg_rerank_score
                            rewritten_avg_score = retry_avg_score
                            
                            # Compare scores and decide whether to use rewritten version
                            improvement = retry_avg_score - avg_rerank_score
                            logger.warning(f"[QueryRewrite] Score comparison: original={avg_rerank_score:.2f}, rewritten={retry_avg_score:.2f}, improvement={improvement:.2f}")
                            
                            if Config.QUERY_REWRITE_RETRY_ON_IMPROVEMENT:
                                # Only use rewritten if it improves score
                                if improvement >= Config.QUERY_REWRITE_MIN_IMPROVEMENT:
                                    logger.warning(f"[QueryRewrite] ✓ Accepting rewritten query (improvement: +{improvement:.2f})")
                                    final_context_chunks = retry_final
                                    question = rewritten_query  # Use rewritten for LLM prompt
                                    query_was_rewritten = True
                                    rewrite_strategy_used = strategy
                                else:
                                    logger.warning(f"[QueryRewrite] ✗ Keeping original query (insufficient improvement: +{improvement:.2f})")
                            else:
                                # Always use rewritten version
                                logger.warning(f"[QueryRewrite] Using rewritten query (retry_on_improvement=False)")
                                final_context_chunks = retry_final
                                question = rewritten_query
                                query_was_rewritten = True
                                rewrite_strategy_used = strategy
                        else:
                            logger.debug(f"[QueryRewrite] Query unchanged after rewriting attempt")
                    
                    except Exception as rewrite_err:
                        logger.error(f"[QueryRewrite] Rewriting failed: {rewrite_err}", exc_info=True)
                        # Continue with original query
                else:
                    logger.info(f"[QueryRewrite] Not triggered - Score too high (avg={avg_rerank_score:.2f} >= {Config.RERANK_QUALITY_THRESHOLD_DECENT})")
            else:
                if not Config.QUERY_REWRITE_ENABLED:
                    logger.info(f"[QueryRewrite] Feature is DISABLED in config")
                elif not final_context_chunks:
                    logger.info(f"[QueryRewrite] Skipped - No chunks retrieved")
            
            # ═══════════════════════════════════════════════════════════
            # 6b. SUBJECT CLASSIFICATION
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
            # 8. STORE MESSAGES IN DATABASE (if session exists)
            # ═══════════════════════════════════════════════════════════
            if session_id:
                # Store user message with rewrite metadata
                user_msg_metadata = None
                if query_was_rewritten:
                    user_msg_metadata = {
                        'query_rewritten': True,
                        'original_query': original_question,
                        'rewritten_query': question,
                        'rewrite_strategy': rewrite_strategy_used,
                        'score_improvement': rewritten_avg_score - original_avg_score
                    }
                
                user_msg = Message(
                    session_id=session_id,
                    role='user',
                    content=question,  # Store the final query (rewritten if applicable)
                    sources=user_msg_metadata  # Store rewrite metadata in sources field
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
                    'web_enabled': web_enabled,
                    # Query rewriting metrics
                    'query_rewritten': query_was_rewritten,
                    'rewrite_strategy': rewrite_strategy_used,
                    'original_query': original_question if query_was_rewritten else None,
                    'rewritten_query': question if query_was_rewritten else None,
                    'score_improvement': (rewritten_avg_score - original_avg_score) if query_was_rewritten else None
                }
            }), 200

    except Exception as e:
        logger.error(f"[Query] Pipeline error: {e}", exc_info=True)
        return jsonify({
            'error': 'An error occurred while processing your question',
            'details': str(e) if current_app.debug else 'Enable debug mode for details'
        }), 500