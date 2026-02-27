import os
from datetime import timedelta
from urllib.parse import quote_plus
from pathlib import Path

# Load .env file from project root, even if python-dotenv is unavailable
env_path = Path(__file__).parent.parent / '.env'

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    # Minimal fallback loader so we don't depend on python-dotenv being installed.
    def load_dotenv(path: Path | str | None = None, override: bool = False):  # type: ignore
        path_obj = Path(path) if path is not None else env_path
        if not path_obj.is_file():
            return False
        try:
            with path_obj.open('r', encoding='utf8') as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if not override and key in os.environ:
                        continue
                    os.environ[key] = value
            return True
        except Exception:
            return False

# Always attempt to load the project .env into the process env
load_dotenv(env_path, override=True)

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

    # Email (SMTP) - used for sending credentials and reset links
    # Supports both SMTP_* (preferred) and MAIL_* (Flask-Mail style) env vars.
    SMTP_HOST = os.getenv('SMTP_HOST') or os.getenv('MAIL_SERVER', '')
    SMTP_PORT = int(os.getenv('SMTP_PORT') or os.getenv('MAIL_PORT') or '0')
    SMTP_USERNAME = os.getenv('SMTP_USERNAME') or os.getenv('MAIL_USERNAME', '')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD') or os.getenv('MAIL_PASSWORD', '')
    # STARTTLS (e.g. 587)
    SMTP_USE_TLS = (os.getenv('SMTP_USE_TLS') or os.getenv('MAIL_USE_TLS') or '0').lower() in ('true', '1', 'yes')
    # SMTPS / SSL (e.g. 465)
    SMTP_USE_SSL = (os.getenv('SMTP_USE_SSL') or os.getenv('MAIL_USE_SSL') or '0').lower() in ('true', '1', 'yes')
    SMTP_FROM = os.getenv('SMTP_FROM') or os.getenv('MAIL_DEFAULT_SENDER') or os.getenv('MAIL_USERNAME') or ''

    # Optional: public login URL to include in credential emails
    APP_PUBLIC_LOGIN_URL = os.getenv('APP_PUBLIC_LOGIN_URL', '')
