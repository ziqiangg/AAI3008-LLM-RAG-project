"""
User auth blueprint  →  /api/users/*
"""
from datetime import timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash

from app.backend.database import get_db_session as get_db
from app.backend.models import User

users_bp = Blueprint('users', __name__)


@users_bp.route('/register', methods=['POST'])
def register():
    data     = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not all([username, email, password]):
        return jsonify({'error': 'username, email, and password are required'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    with get_db() as db:
        if db.query(User).filter_by(email=email).first():
            return jsonify({'error': 'Email already registered'}), 409
        if db.query(User).filter_by(username=username).first():
            return jsonify({'error': 'Username already taken'}), 409

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
        )
        db.add(user)
        db.commit()

        token = create_access_token(
            identity=str(user.id),
            expires_delta=timedelta(days=7),
        )
        return jsonify({'token': token, 'user': user.to_dict()}), 201


@users_bp.route('/login', methods=['POST'])
def login():
    data     = request.get_json(silent=True) or {}
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not all([email, password]):
        return jsonify({'error': 'email and password are required'}), 400

    with get_db() as db:
        user = db.query(User).filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({'error': 'Invalid email or password'}), 401

        token = create_access_token(
            identity=str(user.id),
            expires_delta=timedelta(days=7),
        )
        return jsonify({'token': token, 'user': user.to_dict()}), 200


@users_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    user_id = int(get_jwt_identity())
    with get_db() as db:
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        return jsonify({'user': user.to_dict()}), 200


@users_bp.route('/me', methods=['PATCH'])
@jwt_required()
def update_me():
    user_id = int(get_jwt_identity())
    data    = request.get_json(silent=True) or {}
    with get_db() as db:
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        if 'username' in data:
            user.username = data['username'].strip()
        if 'email' in data:
            user.email = data['email'].strip().lower()
        db.commit()
        return jsonify({'user': user.to_dict()}), 200
