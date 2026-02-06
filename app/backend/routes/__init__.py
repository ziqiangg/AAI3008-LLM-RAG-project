"""
Initialize routes package
"""
from app.backend.routes.health import health_bp
from app.backend.routes.users import users_bp
from app.backend.routes.documents import documents_bp
from app.backend.routes.sessions import sessions_bp
from app.backend.routes.query import query_bp

__all__ = ['health_bp', 'users_bp', 'documents_bp', 'sessions_bp', 'query_bp']
