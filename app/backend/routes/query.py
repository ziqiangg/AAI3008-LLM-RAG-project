"""
Query/RAG routes - Full RAG pipeline implementation
Handles question answering with retrieval, reranking, and generation
"""
import logging
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from datetime import datetime

from app.backend.database import get_db_session
from app.backend.models import Session as ConvSession, Message, Document
from app.backend.services.injestion import get_embeddings
from app.backend.services import retrieval, reranking, generation
from app.backend.config import Config

query_bp = Blueprint('query', __name__)
logger = logging.getLogger(__name__)


@query_bp.route('', methods=['POST'])
def ask_question():
    """
    Ask a question and get AI-generated answer based on uploaded documents.
    
    RAG Pipeline:
    1. Validate input and retrieve session/conversation history
    2. Embed the question using HuggingFace embeddings
    3. Retrieve top K relevant chunks via vector similarity search
    4. Rerank chunks using cross-encoder for precision
    5. Generate answer using Gemini API with context
    6. Store messages in database
    7. Return answer with source citations
    
    Expected JSON payload:
    {
        "question": str (required),
        "session_id": int (optional, creates new if missing),
        "document_ids": [int] (optional, filters to specific documents)
    }
    
    Returns:
    {
        "answer": str,
        "sources": [{chunk_id, document_id, filename, content, score}, ...],
        "session_id": int,
        "metadata": {execution details}
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
        
        session_id = data.get('session_id')
        document_ids = data.get('document_ids')
        
        # Check if user is authenticated (optional)
        current_user_id = None
        try:
            verify_jwt_in_request(optional=True)
            current_user_id = get_jwt_identity()
            if current_user_id:
                current_user_id = int(current_user_id)
        except:
            pass  # Not authenticated, that's okay
        
        with get_db_session() as db:
            conversation_history = []
            
            # ═══════════════════════════════════════════════════════════
            # 2. RETRIEVE SESSION & CONVERSATION HISTORY
            # ═══════════════════════════════════════════════════════════
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
            
            # ═══════════════════════════════════════════════════════════
            # 3. EMBED QUESTION
            # ═══════════════════════════════════════════════════════════
            embeddings_model = get_embeddings()
            question_embedding = embeddings_model.embed_query(question)
            logger.info(f"[Query] Question embedded: {len(question_embedding)} dimensions")
            
            # ═══════════════════════════════════════════════════════════
            # 4. VECTOR RETRIEVAL
            # ═══════════════════════════════════════════════════════════
            retrieved_chunks = retrieval.retrieve_relevant_chunks(
                db_session=db,
                question_embedding=question_embedding,
                document_ids=document_ids,
                top_k=Config.TOP_K_RETRIEVAL
            )
            
            if not retrieved_chunks:
                return jsonify({
                    'answer': "I couldn't find any relevant information in the uploaded documents to answer your question. Please ensure you have uploaded documents or try rephrasing your question.",
                    'sources': [],
                    'session_id': session_id,
                    'metadata': {
                        'num_chunks_retrieved': 0,
                        'num_chunks_reranked': 0,
                        'error': 'No relevant chunks found'
                    }
                }), 200
            
            logger.info(f"[Query] Retrieved {len(retrieved_chunks)} chunks")
            
            # ═══════════════════════════════════════════════════════════
            # 5. RERANK CHUNKS
            # ═══════════════════════════════════════════════════════════
            try:
                reranked_chunks = reranking.rerank_chunks(
                    question=question,
                    chunks=retrieved_chunks,
                    top_k=Config.RERANK_TOP_K
                )
                logger.info(f"[Query] Reranked to top {len(reranked_chunks)} chunks")
            except Exception as e:
                # Fallback: use retrieval results if reranking fails
                logger.warning(f"[Query] Reranking failed, using retrieval results: {e}")
                reranked_chunks = retrieved_chunks[:Config.RERANK_TOP_K]
            
            # ═══════════════════════════════════════════════════════════
            # 6. GENERATE ANSWER
            # ═══════════════════════════════════════════════════════════
            result = generation.generate_answer(
                question=question,
                context_chunks=reranked_chunks,
                conversation_history=conversation_history
            )
            
            answer = result['answer']
            logger.info(f"[Query] Answer generated: {len(answer)} chars")
            
            # ═══════════════════════════════════════════════════════════
            # 7. PREPARE SOURCE CITATIONS
            # ═══════════════════════════════════════════════════════════
            sources = []
            for chunk in reranked_chunks:
                sources.append({
                    'chunk_id': chunk['chunk_id'],
                    'document_id': chunk['document_id'],
                    'filename': chunk['filename'],
                    'content': chunk['content'][:300] + '...' if len(chunk['content']) > 300 else chunk['content'],
                    'score': chunk.get('rerank_score', chunk.get('similarity', 0.0)),
                    'chunk_order': chunk.get('chunk_order', 0)
                })
            
            # ═══════════════════════════════════════════════════════════
            # 8. STORE MESSAGES IN DATABASE (if session exists)
            # ═══════════════════════════════════════════════════════════
            if session_id:
                # Store user message
                user_msg = Message(
                    session_id=session_id,
                    role='user',
                    content=question
                )
                db.add(user_msg)
                
                # Store assistant message with sources
                assistant_msg = Message(
                    session_id=session_id,
                    role='assistant',
                    content=answer,
                    sources={'chunks': [{'chunk_id': s['chunk_id'], 'document_id': s['document_id']} for s in sources]}
                )
                db.add(assistant_msg)
                
                # Auto-generate session title from first question
                if session and session.title == 'New Chat' and len(conversation_history) == 0:
                    session.title = question[:60] + ('...' if len(question) > 60 else '')
                
                db.commit()
                logger.info(f"[Query] Messages stored in session {session_id}")
            
            # ═══════════════════════════════════════════════════════════
            # 9. RETURN RESPONSE
            # ═══════════════════════════════════════════════════════════
            return jsonify({
                'answer': answer,
                'sources': sources,
                'session_id': session_id,
                'metadata': {
                    'model': result['model_used'],
                    'num_chunks_retrieved': len(retrieved_chunks),
                    'num_chunks_reranked': len(reranked_chunks),
                    'num_context_messages': len(conversation_history),
                    'finish_reason': result.get('finish_reason', 'COMPLETED')
                }
            }), 200
        
    except Exception as e:
        logger.error(f"[Query] Pipeline error: {e}", exc_info=True)
        return jsonify({
            'error': 'An error occurred while processing your question',
            'details': str(e) if current_app.debug else 'Enable debug mode for details'
        }), 500
