import sys, os
import pytest

# ensure project root is on sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db


@pytest.fixture
def client():
    """Test client that uses whatever DB the app is configured with.

    This honors your MariaDB/MySQL settings from .env / environment
    (DATABASE_URL or FORCE_MYSQL + MYSQL_*). It only forces FLASK_ENV
    and TESTING flags.
    """
    os.environ.setdefault('FLASK_ENV', 'testing')
    app = create_app()
    app.config.update({
        "TESTING": True,
    })
    with app.app_context():
        try:
            yield app.test_client()
        finally:
            db.session.remove()
