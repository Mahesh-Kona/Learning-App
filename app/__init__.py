from flask import Flask, jsonify, request
import os

from app.extensions import db, migrate, jwt, cors, limiter, cache
from app.routes.auth_routes import auth_bp
from app.api import bp as api_bp
from app.routes.api import api_bp as routes_api_bp
from app.routes.demo_routes import bp as demo_bp
from app.routes.admin_routes import admin_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object('app.config.Config')

  

    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # JWT error handlers (keep payload shape consistent across the API)
    def _jwt_error(message: str, *, code: int, error: str):
        return jsonify({
            "success": False,
            "error": error,
            "msg": message,
            "code": code,
        }), code

    @jwt.expired_token_loader
    def _expired_token_callback(jwt_header, jwt_payload):
        return _jwt_error("Token has expired", code=401, error="token_expired")

    @jwt.invalid_token_loader
    def _invalid_token_callback(message):
        # e.g. "Signature verification failed"
        return _jwt_error(message or "Invalid token", code=422, error="invalid_token")

    @jwt.unauthorized_loader
    def _missing_token_callback(message):
        # e.g. "Missing Authorization Header"
        return _jwt_error(message or "Authorization required", code=401, error="authorization_required")

    @jwt.needs_fresh_token_loader
    def _needs_fresh_token_callback(jwt_header, jwt_payload):
        return _jwt_error("Fresh token required", code=401, error="fresh_token_required")

    @jwt.revoked_token_loader
    def _revoked_token_callback(jwt_header, jwt_payload):
        return _jwt_error("Token has been revoked", code=401, error="token_revoked")
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}},
        supports_credentials=app.config.get('CORS_SUPPORTS_CREDENTIALS', True),
        methods=app.config.get('CORS_METHODS', ['GET','POST','PUT','DELETE','OPTIONS']),
        allow_headers=app.config.get('CORS_ALLOW_HEADERS', ['Authorization','Content-Type'])
    )
    # Initialize limiter with storage URI if provided (Redis) and set default limits
    limiter_storage = app.config.get('RATELIMIT_STORAGE_URL')
    default_limits = app.config.get('RATELIMIT_DEFAULTS')
    limiter_kwargs = {}
    if limiter_storage:
        limiter_kwargs['storage_uri'] = limiter_storage
    # Do not pass default_limits directly to init_app (not accepted by all limiter versions)
    # Instead, expose parsed defaults in app.config for potential use.
    if default_limits:
        if isinstance(default_limits, str) and (';' in default_limits or ',' in default_limits):
            parts = [p.strip() for p in default_limits.replace(';', ',').split(',') if p.strip()]
        else:
            parts = [default_limits]
        app.config['RATELIMIT_DEFAULTS'] = parts
    limiter.init_app(app, **limiter_kwargs)
    # Initialize cache (will pick RedisCache if configured)
    cache.init_app(app)

    # Blueprints
    # API blueprint (v1 endpoints under /api/v1/... via the route definitions)
    app.register_blueprint(api_bp, url_prefix="/api/v1")
    # Also register the older routes-based API blueprint which declares its
    # own `url_prefix='/api/v1'` in `app/routes/api.py`. This ensures routes
    # defined there (including dynamic meta endpoints) are available.
    try:
        app.register_blueprint(routes_api_bp)
    except Exception:
        app.logger.debug('routes_api_bp not registered or already present')
    # Auth routes are currently defined as full paths; register without prefix to keep existing routes
    app.register_blueprint(auth_bp)
    # Demo page for browser verification
    app.register_blueprint(demo_bp)
    # Admin login/dashboard
    app.register_blueprint(admin_bp)

    # If using local sqlite, initialize the DB (create tables) automatically in dev
    try:
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '') or ''
        if db_uri.startswith('sqlite'):
            # derive file path and create parent directories as needed
            # ignore in-memory sqlite
            if db_uri != 'sqlite:///:memory:' and 'dev.sqlite' in db_uri:
                db_path = db_uri.split('///')[-1]
                inst_dir = os.path.dirname(db_path)
                os.makedirs(inst_dir, exist_ok=True)
                with app.app_context():
                    try:
                        db.create_all()
                        app.logger.info('Initialized sqlite DB at %s', db_path)
                    except Exception:
                        app.logger.exception('Failed to initialize sqlite DB')
    except Exception:
        app.logger.exception('Error while attempting to initialize DB')

    # Specific handler for oversized requests (return JSON for AJAX callers)
    try:
        from werkzeug.exceptions import RequestEntityTooLarge

        @app.errorhandler(RequestEntityTooLarge)
        def handle_request_entity_too_large(e):
            # If client expects JSON (XHR or Accept header), return structured JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept', '').startswith('application/json'):
                return jsonify({"success": False, "error": "request too large", "code": 413}), 413
            # otherwise return a simple JSON message as well (avoid HTML default)
            return jsonify({"success": False, "error": str(e), "code": 413}), 413
    except Exception:
        # If werkzeug isn't available for any reason, skip this specific handler
        app.logger.debug('RequestEntityTooLarge handler not registered')

    # Global JSON error handler for other exceptions
    @app.errorhandler(Exception)
    def handle_error(e):
        code = getattr(e, 'code', 500)
        return jsonify({
            "success": False,
            "error": str(e),
            "code": code
        }), code

    # Security headers and small hardening
    @app.after_request
    def set_security_headers(response):
        # Basic headers (adjust as needed in production)
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'no-referrer')
        response.headers.setdefault('X-XSS-Protection', '1; mode=block')
        # Add Content Security Policy header from config
        csp = app.config.get('CONTENT_SECURITY_POLICY')
        if csp:
            response.headers.setdefault('Content-Security-Policy', csp)
        return response

    @app.route('/csp-report', methods=['POST'])
    def csp_report():
        # Accept and log CSP violation reports from browsers (Content-Security-Policy-Report-Only or report-uri)
        try:
            data = request.get_json(silent=True)
            app.logger.warning('CSP report: %s', data)
            # also persist reports to a log file for later analysis
            try:
                import json
                logs_dir = os.path.join(app.instance_path, 'logs')
                os.makedirs(logs_dir, exist_ok=True)
                fp = os.path.join(logs_dir, 'csp_reports.jsonl')
                with open(fp, 'a', encoding='utf8') as fh:
                    fh.write(json.dumps({'ts': __import__('time').time(), 'report': data}) + '\n')
            except Exception:
                app.logger.exception('Failed to persist CSP report')
        except Exception:
            app.logger.exception('Failed to parse CSP report')
        return ('', 204)

    @app.route('/')
    def home():
        # Serve the admin login page at the root (index)
        try:
            # Always render the site's index.html at the root.
            # Do not redirect automatically to the admin dashboard — the user requested the
            # root URL always show the index page.
            from flask import render_template
            return render_template('index.html')
        except Exception:
            return jsonify({"message": "Flask Learning Backend is running 🚀"})

    @app.route('/manage-cards.html')
    def manage_cards_page():
        """Render the topic card management UI.

        Expects optional query params: lesson_id, topic_id, course_id.
        """
        from flask import render_template as _rt
        lesson_id = request.args.get('lesson_id')
        topic_id = request.args.get('topic_id')
        course_id = request.args.get('course_id')
        return _rt('manage-cards.html', lesson_id=lesson_id, topic_id=topic_id, course_id=course_id)

    # Serve uploaded files from UPLOAD_PATH in development
    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        from flask import send_from_directory
        up = app.config.get('UPLOAD_PATH', '/tmp/uploads')
        # resolve relative upload paths relative to the application root
        try:
            if not os.path.isabs(up):
                resolved_up = os.path.join(app.root_path, up)
            else:
                resolved_up = up
            # safety: ensure the directory exists and file is present
            fp = os.path.join(resolved_up, filename)
            if os.path.exists(fp):
                return send_from_directory(resolved_up, filename)

            # Fallback: also check project-root uploads directory explicitly
            project_root = os.path.abspath(os.path.join(app.root_path, '..'))
            alt_up = os.path.join(project_root, 'uploads')
            # If the incoming filename accidentally includes a leading 'uploads/' segment, strip it for alt search
            alt_filename = filename
            if alt_filename.lower().startswith('uploads/'):
                alt_filename = alt_filename.split('/', 1)[1]
            alt_fp = os.path.join(alt_up, alt_filename)
            if os.path.exists(alt_fp):
                return send_from_directory(alt_up, alt_filename)

            app.logger.debug('Uploaded file not found: %s; checked %s and %s', filename, fp, alt_fp)
            return jsonify({'success': False, 'error': 'file not found', 'code': 404}), 404
        except Exception as e:
            app.logger.exception('Failed to serve uploaded file')
            return jsonify({'success': False, 'error': 'file not found', 'code': 404}), 404

    # Debug helper: expose selected runtime config (only when app.debug is True)
    @app.route('/__debug/config')
    def debug_config():
        if not app.debug:
            return jsonify({'error': 'debug only'}), 403
        try:
            return jsonify({
                'SQLALCHEMY_DATABASE_URI': app.config.get('SQLALCHEMY_DATABASE_URI'),
                'UPLOAD_PATH': app.config.get('UPLOAD_PATH'),
                'MAX_CONTENT_LENGTH': app.config.get('MAX_CONTENT_LENGTH'),
                'FORCE_MYSQL': app.config.get('FORCE_MYSQL'),

                # Email (non-sensitive diagnostics)
                'SMTP_HOST_set': bool(app.config.get('SMTP_HOST')),
                'SMTP_PORT': app.config.get('SMTP_PORT'),
                'SMTP_USE_SSL': bool(app.config.get('SMTP_USE_SSL')),
                'SMTP_USE_TLS': bool(app.config.get('SMTP_USE_TLS')),
                'SMTP_FROM_set': bool(app.config.get('SMTP_FROM')),
                'APP_PUBLIC_LOGIN_URL_set': bool(app.config.get('APP_PUBLIC_LOGIN_URL')),
            })
        except Exception:
            app.logger.exception('Failed to return debug config')
            return jsonify({'error': 'failed to read config'}), 500

    return app
