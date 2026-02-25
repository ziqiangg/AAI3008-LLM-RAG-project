"""
Conversation session blueprint  →  /api/sessions/*
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.backend.database import get_db_session as get_db
from app.backend.models import Session as ConvSession, Message

sessions_bp = Blueprint('sessions', __name__)


@sessions_bp.route('/', methods=['POST'])
@jwt_required()
def create_session():
    user_id = int(get_jwt_identity())
    data    = request.get_json(silent=True) or {}
    with get_db() as db:
        s = ConvSession(
            user_id=user_id,
            title=data.get('title', 'New Chat'),
            document_ids=data.get('document_ids', []),
        )
        db.add(s)
        db.commit()
        return jsonify({'session': s.to_dict()}), 201


@sessions_bp.route('/', methods=['GET'])
@jwt_required()
def list_sessions():
    user_id = int(get_jwt_identity())
    with get_db() as db:
        sessions = (
            db.query(ConvSession)
            .filter_by(user_id=user_id)
            .order_by(ConvSession.last_accessed.desc())
            .all()
        )
        return jsonify({'sessions': [s.to_dict() for s in sessions]}), 200


@sessions_bp.route('/<int:session_id>', methods=['GET'])
@jwt_required()
def get_session(session_id):
    user_id = int(get_jwt_identity())
    with get_db() as db:
        s = db.query(ConvSession).filter_by(id=session_id, user_id=user_id).first()
        if not s:
            return jsonify({'error': 'Session not found'}), 404
        result = s.to_dict()
        result['messages'] = [m.to_dict() for m in s.messages]
        return jsonify(result), 200


@sessions_bp.route('/<int:session_id>', methods=['PATCH'])
@jwt_required()
def update_session(session_id):
    user_id = int(get_jwt_identity())
    data    = request.get_json(silent=True) or {}
    with get_db() as db:
        s = db.query(ConvSession).filter_by(id=session_id, user_id=user_id).first()
        if not s:
            return jsonify({'error': 'Session not found'}), 404
        if 'title'        in data: s.title        = data['title']
        if 'document_ids' in data: s.document_ids = data['document_ids']
        s.last_accessed = datetime.utcnow()
        db.commit()
        return jsonify({'session': s.to_dict()}), 200


@sessions_bp.route('/<int:session_id>', methods=['DELETE'])
@jwt_required()
def delete_session(session_id):
    user_id = int(get_jwt_identity())
    with get_db() as db:
        s = db.query(ConvSession).filter_by(id=session_id, user_id=user_id).first()
        if not s:
            return jsonify({'error': 'Session not found'}), 404
        db.delete(s)   # cascades to messages
        db.commit()
        return jsonify({'message': f'Session {session_id} deleted'}), 200


@sessions_bp.route('/<int:session_id>/messages', methods=['POST'])
@jwt_required()
def add_message(session_id):
    user_id = int(get_jwt_identity())
    data    = request.get_json(silent=True) or {}
    role    = data.get('role', 'user')
    content = data.get('content', '').strip()

    if not content:
        return jsonify({'error': 'content is required'}), 400
    if role not in ('user', 'assistant'):
        return jsonify({'error': "role must be 'user' or 'assistant'"}), 400

    with get_db() as db:
        s = db.query(ConvSession).filter_by(id=session_id, user_id=user_id).first()
        if not s:
            return jsonify({'error': 'Session not found'}), 404
        msg = Message(
            session_id=session_id,
            role=role,
            content=content,
            sources=data.get('sources'),
        )
        db.add(msg)
        s.last_accessed = datetime.utcnow()
        # Auto-title from first user message
        if role == 'user' and s.title == 'New Chat':
            s.title = content[:60] + ('…' if len(content) > 60 else '')
        db.commit()
        return jsonify({'message': msg.to_dict()}), 201


@sessions_bp.route('/<int:session_id>/messages', methods=['GET'])
@jwt_required()
def get_messages(session_id):
    user_id = int(get_jwt_identity())
    with get_db() as db:
        s = db.query(ConvSession).filter_by(id=session_id, user_id=user_id).first()
        if not s:
            return jsonify({'error': 'Session not found'}), 404
        return jsonify({'messages': [m.to_dict() for m in s.messages]}), 200
