"""
Query/RAG routes - Full RAG pipeline implementation
Handles question answering with retrieval, reranking, and generation
"""
import logging
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from datetime import datetime

from app.backend.database import get_db_session
from app.backend.models import Session as ConvSession, Message, SessionMemory
from app.backend.services.injestion import get_embeddings
from app.backend.services import retrieval, reranking, generation, classification,web_retrieval
from app.backend.services.query_rewriter import get_query_rewriter
from app.backend.config import Config
from app.backend.services.tool_detection import detect_and_generate_tool
from app.backend.services.tool_router import decide_tool_routing
from app.backend.services.session_memory_updater import (
    default_structured_memory,
    normalize_structured_memory,
    update_structured_memory_from_query,
)

import os
print(">>> LOADED query.py from:", os.path.abspath(__file__), flush=True)
# Language support: detect_language for identifying query language
from app.backend.services.translation import detect_language

query_bp = Blueprint('query', __name__)
logger = logging.getLogger(__name__)


def _build_rewrite_context(conversation_history: list) -> list:
    """Build compact rewrite context: last user turns + summarized assistant facts."""
    if not conversation_history:
        return []

    max_user_turns = int(getattr(Config, 'WORKING_MEMORY_USER_TURNS', 3) or 3)
    user_turns = [m for m in conversation_history if m.get('role') == 'user'][-max_user_turns:]

    assistant_msgs = [m for m in conversation_history if m.get('role') == 'assistant']
    assistant_facts = []
    for msg in assistant_msgs[-2:]:
        content = (msg.get('content') or '').strip()
        if not content:
            continue
        # Lightweight factual condensation: first sentence / short span.
        first = content.split('\n')[0].strip()
        first = first[:220]
        if first:
            assistant_facts.append(first)

    rewrite_ctx = list(user_turns)
    if assistant_facts:
        rewrite_ctx.append({
            'role': 'assistant',
            'content': "Factual summary from previous assistant responses: " + " | ".join(assistant_facts)
        })
    return rewrite_ctx


def _ensure_web_coverage_in_context(question: str, final_context_chunks: list, web_chunks: list) -> list:
    """Ensure at least one web chunk is present when web retrieval returned results."""
    if not final_context_chunks or not web_chunks:
        return final_context_chunks

    has_web = any((c.get('metadata') or {}).get('source_type') == 'web' for c in final_context_chunks)
    if has_web:
        return final_context_chunks

    try:
        top_web = reranking.rerank_chunks(
            question=question,
            chunks=web_chunks,
            top_k=1,
        )
        if not top_web:
            return final_context_chunks

        # Keep context window size stable: replace the last slot with best web chunk.
        merged = list(final_context_chunks)
        if len(merged) >= Config.RERANK_TOP_K:
            merged[-1] = top_web[0]
        else:
            merged.append(top_web[0])
        return merged
    except Exception:
        return final_context_chunks


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
        original_user_question = question
        session_id = data.get('session_id')
        document_ids = data.get('document_ids')
        folder_ids = data.get('folder_ids')  # NEW: folder filtering support

        # Centralized routing decision (single source of truth for intent checks)
        web_toggle = bool(data.get('web_search', False))
        diagram_toggle = bool(data.get('diagram', False))
        routing_decision = decide_tool_routing(
            original_query=original_user_question,
            effective_query=question,
            web_toggle=web_toggle,
            diagram_toggle=diagram_toggle,
        )
        web_enabled = routing_decision.web_enabled
        diagram_enabled = routing_decision.diagram_enabled

        # Check if user is authenticated (optional)
        current_user_id = None
        try:
            verify_jwt_in_request(optional=True)
            current_user_id = get_jwt_identity()
            if current_user_id:
                current_user_id = int(current_user_id)
        except Exception:
            pass  # Not authenticated, that's okay

        if session_id and not current_user_id:
            return jsonify({'error': 'Authentication required for session-based queries'}), 401

        with get_db_session() as db:
            conversation_history = []
            rewrite_context_history = []
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

                # Session-bound queries are authenticated; enforce ownership.
                if session.user_id != current_user_id:
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
                    {'role': msg.role, 'content': msg.content, 'sources': msg.sources}
                    for msg in messages
                ]

                rewrite_context_history = _build_rewrite_context(conversation_history)

                # Update session last accessed
                session.last_accessed = datetime.utcnow()

                # Use session's document_ids if not provided in request
                if not document_ids and session.document_ids:
                    document_ids = session.document_ids
            
            # ═══════════════════════════════════════════════════════════
            # FOLDER FILTERING: Resolve folder_ids to document_ids
            # ═══════════════════════════════════════════════════════════
            if folder_ids and isinstance(folder_ids, list) and len(folder_ids) > 0:
                from app.backend.models import Document as DocModel
                folder_doc_rows = (
                    db.query(DocModel.id)
                    .filter(
                        DocModel.folder_id.in_(folder_ids)
                    )
                    .all()
                )
                folder_doc_ids = [r.id for r in folder_doc_rows]
                
                # Merge with explicit document_ids (if both provided, use intersection)
                if document_ids:
                    document_ids = list(set(document_ids) & set(folder_doc_ids))
                else:
                    document_ids = folder_doc_ids
                
                logger.info(f"[Query] Folder filter: {folder_ids} → {len(document_ids)} docs")

            logger.info(f"[Query] Question: '{question[:50]}...'")
            logger.info(f"[Query] Session: {session_id}, Documents: {document_ids}, History: {len(conversation_history)} msgs")
            logger.info(
                f"[Query] Web enabled: {web_enabled} "
                f"(toggle={web_toggle}, explicit={routing_decision.web_requested_explicit})"
            )

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
                user_id=current_user_id,
                top_k=Config.TOP_K_RETRIEVAL
            )
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

            if not all_chunks:
                return jsonify({
                    'answer': (
                        "I couldn't find any relevant information in the available sources to answer your question. "
                        "Please upload documents, enable web search, or try rephrasing your question."
                    ),
                    'sources': [],
                    'session_id': session_id,
                    'metadata': {
                        'num_chunks_retrieved': 0,
                        'num_chunks_reranked': 0,
                        'num_web_chunks': 0,
                        'error': 'No relevant chunks found in docs or web'
                    }
                }), 200

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

            # If web retrieval was enabled and returned results, retain at least one web item
            # in final context to avoid doc-only drift for explicit online/current requests.
            if web_enabled and web_chunks:
                final_context_chunks = _ensure_web_coverage_in_context(
                    question=question,
                    final_context_chunks=final_context_chunks,
                    web_chunks=web_chunks,
                )

            # ═══════════════════════════════════════════════════════════
            # 6a. ADAPTIVE QUERY REWRITING (Phase 1 & 2)
            #     Triggered when relevance scores are low or conversational context needed
            # ═══════════════════════════════════════════════════════════
            # Initialize rewriting tracking variables (always set to avoid UnboundLocalError)
            original_question = question  # Preserve original for logging
            query_was_rewritten = False
            rewrite_strategy_used = None
            accepted_rewritten_query = None
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
                logger.warning(f"[QueryRewrite] Rewrite context messages: {len(rewrite_context_history) if rewrite_context_history else 0}")
                
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
                    if rewrite_context_history and len(rewrite_context_history) >= 2:
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
                                conversation_history=rewrite_context_history,
                                avg_rerank_score=avg_rerank_score
                            )
                            # HyDE can distort intent for explicit diagram requests.
                            # Keep query semantics closer to user phrasing for visual tasks.
                            if routing_decision.diagram_requested_explicit and strategy == 'hyde':
                                strategy = 'expansion'
                            logger.warning(f"[QueryRewrite] Auto-selected strategy: {strategy}")
                        else:
                            # Default to conversation context fusion
                            strategy = 'conversation_context'
                        
                        # Apply rewriting strategy
                        rewritten_query = None
                        use_original_for_rerank = False  # Default: use rewritten query for reranking
                        
                        if strategy == 'conversation_context':
                            rewritten_query = query_rewriter.rewrite_with_conversation_context(
                                current_query=question,
                                conversation_history=rewrite_context_history
                            )
                        elif strategy == 'expansion':
                            variants = query_rewriter.expand_query_with_synonyms(
                                original_query=question,
                                num_variants=Config.QUERY_REWRITE_MAX_VARIANTS
                            )
                            # expand_query_with_synonyms returns [original, alt1, alt2...].
                            # Use the first alternative variant for rewrite/retrieval.
                            rewritten_query = variants[1] if variants and len(variants) > 1 else question
                        elif strategy == 'decomposition':
                            sub_questions = query_rewriter.decompose_complex_query(question)
                            
                            # Multi-query retrieval: retrieve chunks for each sub-question
                            if sub_questions and len(sub_questions) > 1:
                                logger.warning(f"[QueryRewrite] Multi-query retrieval for {len(sub_questions)} sub-questions")
                                embeddings_model = get_embeddings()
                                all_chunks = {}  # Deduplicate by chunk_id, keep best score
                                
                                for idx, sub_q in enumerate(sub_questions, 1):
                                    logger.warning(f"  Sub-Q{idx}: {sub_q}")
                                    sub_embedding = embeddings_model.embed_query(sub_q)
                                    sub_chunks = retrieval.retrieve_relevant_chunks(
                                        db_session=db,
                                        question_embedding=sub_embedding,
                                        document_ids=document_ids,
                                        user_id=current_user_id,
                                        top_k=Config.TOP_K_RETRIEVAL
                                    )
                                    # Merge chunks, keeping best distance for duplicates
                                    for chunk in sub_chunks:
                                        chunk_id = chunk['chunk_id']
                                        if chunk_id not in all_chunks or chunk['distance'] < all_chunks[chunk_id]['distance']:
                                            all_chunks[chunk_id] = chunk
                                
                                retry_chunks = list(all_chunks.values())
                                logger.info(f"[QueryRewrite] Retrieved {len(retry_chunks)} unique chunks from multi-query")
                                
                                # Keep joined sub-questions for logging/tracking
                                # But we'll use original query for reranking (see below)
                                rewritten_query = " | ".join(sub_questions)
                                use_original_for_rerank = True  # Flag to use original question in reranking
                            else:
                                # Single sub-question or fallback to original
                                rewritten_query = sub_questions[0] if sub_questions else question
                                use_original_for_rerank = False
                        elif strategy == 'hyde':
                            hypothetical_doc = query_rewriter.generate_hypothetical_document(question)
                            # Embed the hypothetical document instead of query
                            rewritten_query = hypothetical_doc
                            # For HyDE, rerank against the original question to preserve intent.
                            use_original_for_rerank = True
                        else:
                            rewritten_query = question
                        
                        # If query was actually rewritten, retry retrieval
                        if rewritten_query and rewritten_query != question:
                            # Check if decomposition already did multi-query retrieval
                            multi_query_done = (strategy == 'decomposition' and 
                                              sub_questions and len(sub_questions) > 1)
                            
                            if not multi_query_done:
                                # Single query strategies - do normal retrieval
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
                                    user_id=current_user_id,
                                    top_k=Config.TOP_K_RETRIEVAL
                                )
                            # else: multi-query decomposition already set retry_chunks
                            
                            # Re-rank with appropriate query
                            # For multi-query decomposition, use original question for reranking
                            rerank_question = question if use_original_for_rerank else rewritten_query
                            retry_final = reranking.rerank_chunks(
                                question=rerank_question,
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
                                    # Keep retrieval rewrite separate from user-facing question.
                                    accepted_rewritten_query = rewritten_query
                                    query_was_rewritten = True
                                    rewrite_strategy_used = strategy
                                else:
                                    logger.warning(f"[QueryRewrite] ✗ Keeping original query (insufficient improvement: +{improvement:.2f})")
                            else:
                                # Always use rewritten version
                                logger.warning(f"[QueryRewrite] Using rewritten query (retry_on_improvement=False)")
                                final_context_chunks = retry_final
                                # Keep retrieval rewrite separate from user-facing question.
                                accepted_rewritten_query = rewritten_query
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

            # Rewrite acceptance can replace final chunks; re-apply web-presence guarantee.
            if web_enabled and web_chunks:
                final_context_chunks = _ensure_web_coverage_in_context(
                    question=question,
                    final_context_chunks=final_context_chunks,
                    web_chunks=web_chunks,
                )
            
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

            # Re-evaluate routing with effective (possibly rewritten) query.
            routing_decision = decide_tool_routing(
                original_query=original_user_question,
                effective_query=original_user_question,
                web_toggle=web_toggle,
                diagram_toggle=diagram_toggle,
            )
            web_enabled = routing_decision.web_enabled
            diagram_enabled = routing_decision.diagram_enabled

            # ═══════════════════════════════════════════════════════════
            # GENERATE ANSWER IN USER'S LANGUAGE
            # ═══════════════════════════════════════════════════════════
            result = generation.generate_answer(
                question=question,
                context_chunks=final_context_chunks,
                conversation_history=conversation_history,
                subject_context=subject_context,
                language_info=language_info,
                web_enabled=web_enabled,
                diagram_enabled=diagram_enabled,
                web_requested=routing_decision.web_requested_explicit,
                diagram_requested=routing_decision.diagram_requested_explicit,
            )

            answer = result['answer']
            
            # Only generate diagrams if diagram mode is enabled
            tool_output = None
            if diagram_enabled:
                try:
                    tool_output = detect_and_generate_tool(
                        question=question,
                        context_chunks=final_context_chunks
                    )
                    if (tool_output is None) and routing_decision.diagram_requested_explicit:
                        logger.warning("[Tool] Explicit diagram request detected; forcing Mermaid fallback")
                        tool_output = detect_and_generate_tool(
                            question=question,
                            context_chunks=final_context_chunks,
                            forced_type='MERMAID'
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

            # Source mix metadata is reused for response + session-memory provenance.
            num_doc_chunks = sum(1 for c in final_context_chunks if c.get('metadata', {}).get('source_type') != 'web')
            num_web_chunks = len(final_context_chunks) - num_doc_chunks

            # ═══════════════════════════════════════════════════════════
            # 8. STORE MESSAGES IN DATABASE (if session exists)
            # ═══════════════════════════════════════════════════════════
            # 8. STORE MESSAGES IN DATABASE (if session exists)
            # ═══════════════════════════════════════════════════════════
            if session_id:
                # Determine first-turn status before inserting new messages.
                had_prior_messages = (
                    db.query(Message)
                    .filter_by(session_id=session_id)
                    .count() > 0
                )

                # Store user message with rewrite metadata
                user_msg_metadata = None
                if query_was_rewritten:
                    user_msg_metadata = {
                        'query_rewritten': True,
                        'original_query': original_question,
                        'rewritten_query': accepted_rewritten_query,
                        'rewrite_strategy': rewrite_strategy_used,
                        'score_improvement': rewritten_avg_score - original_avg_score
                    }
                
                user_msg = Message(
                    session_id=session_id,
                    role='user',
                    content=original_question,
                    sources=user_msg_metadata  # Store rewrite metadata in sources field
                )
                db.add(user_msg)

                assistant_msg = Message(
                    session_id=session_id,
                    role='assistant',
                    content=answer,
                    sources={'chunks': sources, 'tool': tool_output}
                )
                db.add(assistant_msg)
                db.flush()

                # Per-query memory auto-refresh with provenance.
                mem = db.query(SessionMemory).filter_by(session_id=session_id).first()
                if not mem:
                    mem = SessionMemory(
                        session_id=session_id,
                        structured_data=default_structured_memory(),
                        freeform_text='',
                        freeform_enabled=0,
                        latest_diagram_artifact=None,
                    )
                    db.add(mem)

                mem.structured_data = update_structured_memory_from_query(
                    structured_data=normalize_structured_memory(mem.structured_data),
                    original_question=original_question,
                    answer=answer,
                    user_message_id=user_msg.id,
                    assistant_message_id=assistant_msg.id,
                    rewrite_strategy=rewrite_strategy_used,
                    rewritten_query=accepted_rewritten_query,
                    score_improvement=(rewritten_avg_score - original_avg_score) if query_was_rewritten else None,
                    web_enabled=web_enabled,
                    diagram_enabled=diagram_enabled,
                    web_requested_explicit=routing_decision.web_requested_explicit,
                    diagram_requested_explicit=routing_decision.diagram_requested_explicit,
                    num_doc_chunks=num_doc_chunks,
                    num_web_chunks=num_web_chunks,
                )

                if isinstance(tool_output, dict):
                    t = tool_output.get('type')
                    if t == 'mermaid' and tool_output.get('code'):
                        mem.latest_diagram_artifact = {
                            'type': 'mermaid',
                            'mermaid': tool_output.get('code'),
                        }
                    elif t == 'desmos' and tool_output.get('expressions'):
                        mem.latest_diagram_artifact = {
                            'type': 'desmos',
                            'desmos': tool_output.get('expressions'),
                        }

                # Auto-generate session title from first question only
                if session and session.title == 'New Chat':
                    if not had_prior_messages:
                        session.title = question[:60] + ('...' if len(question) > 60 else '')

                db.commit()
                logger.info(f"[Query] Messages stored in session {session_id}")

            # ═══════════════════════════════════════════════════════════
            # 9. RETURN RESPONSE
            # ═══════════════════════════════════════════════════════════
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
                    'diagram_enabled': diagram_enabled,
                    'web_requested_explicit': routing_decision.web_requested_explicit,
                    'diagram_requested_explicit': routing_decision.diagram_requested_explicit,
                    # Query rewriting metrics
                    'query_rewritten': query_was_rewritten,
                    'rewrite_strategy': rewrite_strategy_used,
                    'original_query': original_question if query_was_rewritten else None,
                    'rewritten_query': accepted_rewritten_query if query_was_rewritten else None,
                    'score_improvement': (rewritten_avg_score - original_avg_score) if query_was_rewritten else None
                }
            }), 200

    except Exception as e:
        logger.error(f"[Query] Pipeline error: {e}", exc_info=True)
        return jsonify({
            'error': 'An error occurred while processing your question',
            'details': str(e) if current_app.debug else 'Enable debug mode for details'
        }), 500