"""
Conversation session blueprint  →  /api/sessions/*
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.backend.database import get_db_session as get_db
from app.backend.models import Session as ConvSession, Message, SessionMemory
from app.backend.services.memory_validator import validate_memory_payload
from app.backend.services.session_memory_updater import (
    default_structured_memory,
    is_structured_memory_empty,
    extract_latest_diagram_artifact,
    build_bootstrap_structured_memory_from_messages,
    normalize_structured_memory,
)

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
        # Auto-title logic removed - handled by query endpoint to avoid race condition
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


def _default_structured_memory():
    return default_structured_memory()


def _is_structured_memory_empty(structured):
    return is_structured_memory_empty(structured)


def _extract_latest_diagram_artifact(messages):
    return extract_latest_diagram_artifact(messages)


def _bootstrap_structured_memory_from_messages(messages):
    return build_bootstrap_structured_memory_from_messages(messages)


@sessions_bp.route('/<int:session_id>/memory', methods=['GET'])
@jwt_required()
def get_session_memory(session_id):
    user_id = int(get_jwt_identity())
    with get_db() as db:
        s = db.query(ConvSession).filter_by(id=session_id, user_id=user_id).first()
        if not s:
            return jsonify({'error': 'Session not found'}), 404

        session_messages = (
            db.query(Message)
            .filter_by(session_id=session_id)
            .order_by(Message.created_at.asc())
            .all()
        )

        mem = db.query(SessionMemory).filter_by(session_id=session_id).first()
        if not mem:
            mem = SessionMemory(
                session_id=session_id,
                structured_data=_bootstrap_structured_memory_from_messages(session_messages),
                freeform_text='',
                freeform_enabled=0,
                latest_diagram_artifact=_extract_latest_diagram_artifact(session_messages),
            )
            db.add(mem)
            db.flush()
        else:
            mem.structured_data = normalize_structured_memory(mem.structured_data)
            if _is_structured_memory_empty(mem.structured_data):
                mem.structured_data = _bootstrap_structured_memory_from_messages(session_messages)
            if mem.latest_diagram_artifact is None:
                mem.latest_diagram_artifact = _extract_latest_diagram_artifact(session_messages)

        return jsonify({'memory': mem.to_dict()}), 200


@sessions_bp.route('/<int:session_id>/memory', methods=['PATCH'])
@jwt_required()
def update_session_memory(session_id):
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    ok, err = validate_memory_payload(data)
    if not ok:
        return jsonify({'error': err}), 400

    with get_db() as db:
        s = db.query(ConvSession).filter_by(id=session_id, user_id=user_id).first()
        if not s:
            return jsonify({'error': 'Session not found'}), 404

        mem = db.query(SessionMemory).filter_by(session_id=session_id).first()
        if not mem:
            mem = SessionMemory(session_id=session_id)
            db.add(mem)

        structured_data = normalize_structured_memory(data.get('structured_data') or _default_structured_memory())
        freeform_enabled = 1 if bool(data.get('freeform_enabled', False)) else 0
        freeform_text = data.get('freeform_text') if freeform_enabled else ''

        # Keep only most recent mermaid/desmos artifact if provided.
        latest_artifact = data.get('latest_diagram_artifact')
        if isinstance(latest_artifact, dict):
            t = latest_artifact.get('type')
            if t not in ('mermaid', 'desmos'):
                latest_artifact = None
        else:
            latest_artifact = None

        mem.structured_data = structured_data
        mem.freeform_enabled = freeform_enabled
        mem.freeform_text = freeform_text or ''
        if latest_artifact is not None:
            mem.latest_diagram_artifact = latest_artifact

        s.last_accessed = datetime.utcnow()
        db.flush()
        return jsonify({'memory': mem.to_dict()}), 200
