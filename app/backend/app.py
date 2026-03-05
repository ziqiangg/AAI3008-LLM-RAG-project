from flask import Flask, jsonify, send_from_directory, make_response
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from app.backend.config import config
from app.backend.database import close_db_session
import os
from datetime import datetime, timedelta

jwt = JWTManager()

def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Ensure JWT secret key is set (can also come from .env)
    app.config["JWT_SECRET_KEY"] = getattr(config, "SECRET_KEY", "dev-secret-key-change-in-production")

    # Configure CORS with explicit settings
    CORS(app, 
         resources={r"/api/*": {"origins": "*"}},
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
         supports_credentials=False)
    
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # initialize JWT with app
    jwt.init_app(app)

    register_blueprints(app)
    register_error_handlers(app)
    register_teardown_handlers(app)

    # ── Frontend ──────────────────────────────────────────────────
    @app.route('/')
    def frontend():
        return send_from_directory(
            os.path.join(os.path.dirname(__file__), '../frontend'),
            'index.html'
        )
        
    # Serve static files from frontend folder with caching
    @app.route('/<path:filename>')
    def serve_static(filename):
        # Determine cache duration based on file type
        cache_timeout = 0
        if filename.endswith(('.css', '.js')):
            cache_timeout = 31536000  # 1 year for CSS/JS
        elif filename.endswith(('.svg', '.png', '.jpg', '.jpeg', '.gif', '.ico')):
            cache_timeout = 2592000  # 30 days for images
        
        response = make_response(
            send_from_directory(
                os.path.join(os.path.dirname(__file__), '../frontend'),
                filename
            )
        )
        
        if cache_timeout > 0:
            # Add cache headers for performance
            response.headers['Cache-Control'] = f'public, max-age={cache_timeout}'
            expires = datetime.utcnow() + timedelta(seconds=cache_timeout)
            response.headers['Expires'] = expires.strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        return response
        
    # ── Health Check ──────────────────────────────────────────────
    @app.route('/api/health')
    def health():
        return jsonify({'status': 'healthy', 'service': 'rag-backend'}), 200

    return app


def register_blueprints(app):
    from app.backend.routes.users     import users_bp
    from app.backend.routes.documents import documents_bp
    from app.backend.routes.sessions  import sessions_bp
    from app.backend.routes.query     import query_bp
    from app.backend.routes.links     import links_bp   # NEW

    app.register_blueprint(users_bp,     url_prefix='/api/users')
    app.register_blueprint(documents_bp, url_prefix='/api/documents')
    app.register_blueprint(sessions_bp,  url_prefix='/api/sessions')
    app.register_blueprint(query_bp,     url_prefix='/api/query')
    app.register_blueprint(links_bp,     url_prefix='/api/links')


def register_error_handlers(app):
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
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        close_db_session()


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
