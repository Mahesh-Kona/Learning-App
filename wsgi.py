# wsgi.py
"""WSGI entry point for the Flask application.

This file allows you to run the app with 'flask run' or through a WSGI server.
Environment variables are loaded from a .env file via python-dotenv so
that Cloudflare R2 and other config can be managed outside the codebase.
"""

try:
    from dotenv import load_dotenv  # type: ignore
except ModuleNotFoundError:  # Fallback if python-dotenv isn't installed
    def load_dotenv(*args, **kwargs):  # type: ignore
        """No-op fallback when python-dotenv is unavailable."""
        return False

# Load environment variables from .env (if present) before creating the app
load_dotenv()

from app import create_app

# Create the Flask app using the factory function from app/__init__.py
app = create_app()

# Optional: For direct execution (python wsgi.py)
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",  # accessible on all network interfaces
        port=5000,
        debug=True       # disable debug=True in production
    )
