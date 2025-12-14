import os
from datetime import timedelta
from urllib.parse import quote_plus
from pathlib import Path

# Load .env file from project root
try:
    from dotenv import load_dotenv
    # Find the .env file in the project root (parent of app folder)
    env_path = Path(__file__).parent.parent / '.env'
    load_dotenv(env_path, override=True)
except Exception as e:
    # python-dotenv is optional for running the app in minimal environments
    # If it's missing, continue without loading a .env file.
    pass

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", "15")))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "7")))

    # SQLAlchemy
    # Priority: explicit DATABASE_URL env var -> FORCE_MYSQL when set -> local sqlite dev DB
    DATABASE_URL = os.getenv("DATABASE_URL", None)
    FORCE_MYSQL = os.getenv('FORCE_MYSQL', '0') == '1'
    if not DATABASE_URL:
        if FORCE_MYSQL:
            # Build MySQL URL from individual env vars (for docker/dev setups)
            user = os.getenv("MYSQL_USER", "root")
            pw = quote_plus(os.getenv("MYSQL_PASSWORD", "password"))
            host = os.getenv("MYSQL_HOST", "db")
            port = os.getenv("MYSQL_PORT", "3306")
            db = os.getenv("MYSQL_DATABASE", "learning")
            # ensure utf8mb4 charset and proper args
            DATABASE_URL = f"mysql+pymysql://{user}:{pw}@{host}:{port}/{db}?charset=utf8mb4"
        else:
            # Default to a local SQLite database for faster local development and to
            # avoid requiring a running MySQL server. The DB file is placed in the
            # Flask instance folder (instance/dev.sqlite).
            instance_path = os.getenv('FLASK_INSTANCE_PATH', None)
            if not instance_path:
                # Use the default flask instance path (relative to the package)
                instance_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'instance')
            db_file = os.path.join(instance_path, 'dev.sqlite')
            # SQLite URI uses three slashes for absolute paths
            DATABASE_URL = f"sqlite:///{db_file}"

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Pool & recycle (avoid stale connections)
    # For SQLite in-memory testing we avoid passing pool args that are invalid for StaticPool
    if DATABASE_URL.startswith('sqlite'):
        SQLALCHEMY_ENGINE_OPTIONS = {}
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_size": int(os.getenv("POOL_SIZE", 10)),
            "max_overflow": int(os.getenv("MAX_OVERFLOW", 20)),
            "pool_recycle": int(os.getenv("POOL_RECYCLE", 1800)),  # seconds
            "pool_pre_ping": True
        }

    # CORS
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")  # set to your frontend origin(s) in production
    CORS_SUPPORTS_CREDENTIALS = True
    CORS_ALLOW_HEADERS = ["Authorization", "Content-Type"]
    CORS_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]

    # Uploads
    # Default to project-root uploads folder (parent of app): ../uploads
    # Override with UPLOAD_PATH env var for production or custom setups.
    UPLOAD_PATH = os.getenv("UPLOAD_PATH", "../uploads")
    # Allow larger uploads by default (64 MB). Can be overridden with env var MAX_CONTENT_LENGTH.
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 64 * 1024 * 1024))  # 64 MB

    # Caching
    CACHE_TYPE = os.getenv("CACHE_TYPE", "SimpleCache")  # "RedisCache" if using redis
    CACHE_DEFAULT_TIMEOUT = int(os.getenv("CACHE_DEFAULT_TIMEOUT", 300))

    # Redis / cache settings (used when CACHE_TYPE=RedisCache)
    REDIS_URL = os.getenv("REDIS_URL", os.getenv("CACHE_REDIS_URL", None))
    if REDIS_URL:
        CACHE_TYPE = os.getenv("CACHE_TYPE", "RedisCache")
        CACHE_REDIS_URL = REDIS_URL

    # Rate limiter storage (Flask-Limiter)
    RATELIMIT_STORAGE_URL = os.getenv("RATELIMIT_STORAGE_URL", REDIS_URL)

    # Rate limiting
    RATELIMIT_HEADERS_ENABLED = True
    # Default rate limits (comma-separated, can be overridden per route)
    RATELIMIT_DEFAULTS = os.getenv('RATELIMIT_DEFAULTS', '200 per day;50 per hour')

    # Content Security Policy (basic default, override in production)
    # Allow common CDNs used for icons/fonts during development. In production
    # you should tighten this and move third-party assets to trusted hosts.
    CONTENT_SECURITY_POLICY = os.getenv(
        'CONTENT_SECURITY_POLICY',
        "default-src 'self'; img-src 'self' data: https:; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com;"
    )

    # Ensure Flask JSON responses do not escape unicode (keep utf8 characters like emoji)
    JSON_AS_ASCII = False

    # Session lifetime for "remember me" persistent sessions (defaults to 14 days)
    PERMANENT_SESSION_LIFETIME = timedelta(days=int(os.getenv('SESSION_DURATION_DAYS', '14')))

    # Cross-origin admin session support (required for HTTPS and different origins)
    SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'None')
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'True').lower() in ('true', '1')
    SESSION_COOKIE_DOMAIN = os.getenv('SESSION_COOKIE_DOMAIN', None)
