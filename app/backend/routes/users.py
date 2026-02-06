"""
User management routes
"""
from flask import Blueprint, request, jsonify
from app.backend.database import get_db_session
from app.backend.models import User
from sqlalchemy.exc import IntegrityError

users_bp = Blueprint('users', __name__)


@users_bp.route('/', methods=['GET'])
def get_users():
    """Get all users"""
    session = get_db_session()
    try:
        users = session.query(User).all()
        return jsonify([user.to_dict() for user in users]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@users_bp.route('/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """Get user by ID"""
    session = get_db_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        return jsonify(user.to_dict()), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@users_bp.route('/', methods=['POST'])
def create_user():
    """Create a new user"""
    session = get_db_session()
    try:
        data = request.get_json()
        
        if not data or 'username' not in data or 'email' not in data:
            return jsonify({'error': 'Username and email are required'}), 400
        
        user = User(
            username=data['username'],
            email=data['email']
        )
        
        session.add(user)
        session.commit()
        
        return jsonify(user.to_dict()), 201
    except IntegrityError:
        session.rollback()
        return jsonify({'error': 'Username or email already exists'}), 409
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@users_bp.route('/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete a user"""
    session = get_db_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        session.delete(user)
        session.commit()
        
        return jsonify({'message': 'User deleted successfully'}), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()
