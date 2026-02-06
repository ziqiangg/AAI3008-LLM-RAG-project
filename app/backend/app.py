"""
Flask application factory and configuration
"""
from flask import Flask, jsonify
from flask_cors import CORS
from app.backend.config import config
from app.backend.database import close_db_session
import os


def create_app(config_name=None):
    """
    Application factory pattern for creating Flask app
    
    Args:
        config_name: Configuration name ('development', 'production', or 'default')
    
    Returns:
        Flask application instance
    """
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Enable CORS
    CORS(app)
    
    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Register blueprints
    register_blueprints(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register teardown handlers
    register_teardown_handlers(app)
    
    return app


def register_blueprints(app):
    """Register Flask blueprints"""
    from app.backend.routes.health import health_bp
    from app.backend.routes.users import users_bp
    from app.backend.routes.documents import documents_bp
    from app.backend.routes.sessions import sessions_bp
    from app.backend.routes.query import query_bp
    
    app.register_blueprint(health_bp)
    app.register_blueprint(users_bp, url_prefix='/api/users')
    app.register_blueprint(documents_bp, url_prefix='/api/documents')
    app.register_blueprint(sessions_bp, url_prefix='/api/sessions')
    app.register_blueprint(query_bp, url_prefix='/api/query')


def register_error_handlers(app):
    """Register error handlers"""
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Resource not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error'}), 500
    
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({'error': 'Bad request'}), 400


def register_teardown_handlers(app):
    """Register teardown handlers"""
    
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        close_db_session()


# Create application instance
app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
