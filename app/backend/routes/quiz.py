"""
Quiz generation blueprint → /api/quiz/*
Generates MCQ and multi-select quizzes from document chunks via RAG + Gemini
"""
import logging

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.backend.database import get_db_session
from app.backend.services import retrieval, reranking
from app.backend.services.generation import generate_quiz as generate_quiz_content  # ← alias
from app.backend.services.injestion import get_embeddings

quiz_bp = Blueprint('quiz', __name__)
logger  = logging.getLogger(__name__)


@quiz_bp.route('/generate', methods=['POST'])
@jwt_required()
def generate_quiz():                          # ← route function keeps the name
    """
    Generate a quiz grounded in uploaded documents.

    Payload:
    {
        "num_questions": int        (1–20, default 5),
        "difficulty":    str        ("easy"|"medium"|"hard", default "medium"),
        "question_type": str        ("mcq"|"multi_select"|"mixed", default "mcq"),
        "topic":         str        (optional retrieval hint),
        "document_ids":  [int]      (optional, scopes to specific docs)
    }
    """
    try:
        int(get_jwt_identity())
        data = request.get_json(silent=True) or {}

        # ── Validate config ───────────────────────────────────────
        num_questions = min(max(int(data.get('num_questions', 5)), 1), 20)
        difficulty    = data.get('difficulty', 'medium').lower()
        question_type = data.get('question_type', 'mcq').lower()
        topic         = data.get('topic', '').strip()
        document_ids  = data.get('document_ids') or []
        folder_ids    = data.get('folder_ids') or []  # NEW: folder filtering support
        if difficulty not in ('easy', 'medium', 'hard'):
            return jsonify({'error': 'difficulty must be easy, medium, or hard'}), 400
        if question_type not in ('mcq', 'multi_select', 'mixed'):
            return jsonify({'error': 'question_type must be mcq, multi_select, or mixed'}), 400

        # ── Embed retrieval query ─────────────────────────────────
        retrieval_query = topic if topic else 'key concepts definitions important facts'
        embed_model     = get_embeddings()
        query_embedding = embed_model.embed_query(retrieval_query)

        with get_db_session() as db:
            # ── Resolve folder_ids to document_ids ────────────────────
            if folder_ids:
                from app.backend.models import Document as DocModel
                folder_doc_rows = (
                    db.query(DocModel.id)
                    .filter(DocModel.folder_id.in_(folder_ids))
                    .all()
                )
                folder_doc_ids = [r.id for r in folder_doc_rows]
                
                # Merge with explicit document_ids (if both provided, use intersection)
                if document_ids:
                    document_ids = list(set(document_ids) & set(folder_doc_ids))
                else:
                    document_ids = folder_doc_ids
                
                logger.info(f"[Quiz] Folder filter: {folder_ids} → {len(document_ids)} docs")
            
            # ── Retrieve chunks ───────────────────────────────────
            top_k  = min(num_questions * 2, 15)
            chunks = retrieval.retrieve_relevant_chunks(
                db_session         = db,
                question_embedding = query_embedding,
                document_ids       = document_ids if document_ids else None,
                top_k              = top_k
            )

            if not chunks:
                return jsonify({'error': 'No document content found. Please upload documents first.'}), 404

            # ── Rerank ────────────────────────────────────────────
            try:
                chunks = reranking.rerank_chunks(
                    question = retrieval_query,
                    chunks   = chunks,
                    top_k    = min(num_questions * 3, 30)
                )
            except Exception as e:
                logger.warning(f'[Quiz] Reranking failed, using raw retrieval: {e}')
                chunks = chunks[:min(num_questions * 3, 30)]

            # ── Call generation service ───────────────────────────
            try:
                result = generate_quiz_content(      # ← uses the alias
                    num_questions  = num_questions,
                    difficulty     = difficulty,
                    question_type  = question_type,
                    context_chunks = chunks,
                    topic          = topic or None,
                )
            except (ValueError, RuntimeError) as e:
                logger.error(f'[Quiz route] Generation error: {e}')
                return jsonify({'error': str(e)}), 500

            return jsonify({
                'quiz': {
                    'questions': result['questions'],
                    'config': {
                        'num_questions': len(result['questions']),
                        'difficulty':    difficulty,
                        'question_type': question_type,
                        'topic':         topic or None,
                        'document_ids':  document_ids,
                    }
                }
            }), 200

    except Exception as e:
        logger.error(f'[Quiz] Unhandled error: {e}', exc_info=True)
        return jsonify({
            'error':   'Quiz generation failed.',
            'details': str(e) if current_app.debug else 'Enable debug mode for details.'
        }), 500
