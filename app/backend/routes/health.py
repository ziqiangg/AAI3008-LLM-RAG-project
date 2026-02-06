"""
Health check routes
"""
from flask import Blueprint, jsonify
from sqlalchemy import text
from app.backend.database import engine

health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e)
        }), 503


@health_bp.route('/', methods=['GET'])
def index():
    """Root endpoint"""
    return jsonify({
        'message': 'LLM RAG API',
        'version': '1.0.0',
        'endpoints': {
            'health': '/health',
            'users': '/api/users',
            'documents': '/api/documents',
            'sessions': '/api/sessions',
            'query': '/api/query'
        }
    }), 200
