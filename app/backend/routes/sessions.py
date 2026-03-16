"""
Conversation session blueprint  →  /api/sessions/*
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.backend.database import get_db_session as get_db
from app.backend.models import Session as ConvSession, Message, SessionMemory
from app.backend.services.memory_validator import validate_memory_payload

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
    return {
        'factual_summary_short': '',
        'factual_summary_long': '',
        'unresolved_questions': [],
        'entities_and_aliases': [],
    }


def _is_structured_memory_empty(structured):
    if not isinstance(structured, dict):
        return True
    return (
        not (structured.get('factual_summary_short') or '').strip()
        and not (structured.get('factual_summary_long') or '').strip()
        and not (structured.get('unresolved_questions') or [])
        and not (structured.get('entities_and_aliases') or [])
    )


def _extract_latest_diagram_artifact(messages):
    for msg in reversed(messages or []):
        if getattr(msg, 'role', None) != 'assistant':
            continue
        src = msg.sources if isinstance(msg.sources, dict) else {}
        tool = src.get('tool') if isinstance(src, dict) else None
        if not isinstance(tool, dict):
            continue

        tool_type = tool.get('type')
        if tool_type not in ('mermaid', 'desmos'):
            continue

        value = tool.get(tool_type)
        if value:
            return {
                'type': tool_type,
                tool_type: value,
            }
    return None


def _bootstrap_structured_memory_from_messages(messages):
    structured = _default_structured_memory()
    user_messages = [
        (m.content or '').strip() for m in (messages or [])
        if getattr(m, 'role', None) == 'user' and (m.content or '').strip()
    ]
    assistant_messages = [
        (m.content or '').strip() for m in (messages or [])
        if getattr(m, 'role', None) == 'assistant' and (m.content or '').strip()
    ]

    if assistant_messages:
        structured['factual_summary_short'] = assistant_messages[-1][:280]
        structured['factual_summary_long'] = '\n\n'.join(assistant_messages[-2:])[:1600]
    elif user_messages:
        structured['factual_summary_short'] = user_messages[-1][:280]
        structured['factual_summary_long'] = '\n\n'.join(user_messages[-2:])[:1600]

    unresolved = []
    for msg in reversed(user_messages):
        if msg.endswith('?') and msg not in unresolved:
            unresolved.append(msg)
        if len(unresolved) >= 5:
            break
    structured['unresolved_questions'] = list(reversed(unresolved))
    return structured


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

        structured_data = data.get('structured_data') or _default_structured_memory()
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
