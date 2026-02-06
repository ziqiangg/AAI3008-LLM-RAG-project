"""
Session management routes
"""
from flask import Blueprint, request, jsonify
from app.backend.database import get_db_session
from app.backend.models import Session, User
from datetime import datetime

sessions_bp = Blueprint('sessions', __name__)


@sessions_bp.route('/', methods=['GET'])
def get_sessions():
    """Get all sessions (optionally filtered by user_id)"""
    session_db = get_db_session()
    try:
        user_id = request.args.get('user_id', type=int)
        
        if user_id:
            sessions = session_db.query(Session).filter_by(user_id=user_id).all()
        else:
            sessions = session_db.query(Session).all()
        
        return jsonify([s.to_dict() for s in sessions]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session_db.close()


@sessions_bp.route('/<int:session_id>', methods=['GET'])
def get_session(session_id):
    """Get session by ID"""
    session_db = get_db_session()
    try:
        session = session_db.query(Session).filter_by(id=session_id).first()
        if not session:
            return jsonify({'error': 'Session not found'}), 404
        
        # Update last accessed time
        session.last_accessed = datetime.utcnow()
        session_db.commit()
        
        return jsonify(session.to_dict()), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session_db.close()


@sessions_bp.route('/', methods=['POST'])
def create_session():
    """Create a new session"""
    session_db = get_db_session()
    try:
        data = request.get_json()
        
        if not data or 'user_id' not in data:
            return jsonify({'error': 'user_id is required'}), 400
        
        # Check if user exists
        user = session_db.query(User).filter_by(id=data['user_id']).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        session = Session(
            user_id=data['user_id'],
            document_ids=data.get('document_ids', [])
        )
        
        session_db.add(session)
        session_db.commit()
        
        return jsonify(session.to_dict()), 201
    except Exception as e:
        session_db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session_db.close()


@sessions_bp.route('/<int:session_id>', methods=['PUT'])
def update_session(session_id):
    """Update session (e.g., add documents)"""
    session_db = get_db_session()
    try:
        session = session_db.query(Session).filter_by(id=session_id).first()
        if not session:
            return jsonify({'error': 'Session not found'}), 404
        
        data = request.get_json()
        
        if 'document_ids' in data:
            session.document_ids = data['document_ids']
        
        session.last_accessed = datetime.utcnow()
        session_db.commit()
        
        return jsonify(session.to_dict()), 200
    except Exception as e:
        session_db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session_db.close()


@sessions_bp.route('/<int:session_id>', methods=['DELETE'])
def delete_session(session_id):
    """Delete a session"""
    session_db = get_db_session()
    try:
        session = session_db.query(Session).filter_by(id=session_id).first()
        if not session:
            return jsonify({'error': 'Session not found'}), 404
        
        session_db.delete(session)
        session_db.commit()
        
        return jsonify({'message': 'Session deleted successfully'}), 200
    except Exception as e:
        session_db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session_db.close()
