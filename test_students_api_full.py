import json
from app import create_app
from app.api.progress import get_students

app = create_app()
with app.app_context():
    with app.test_request_context('?limit=10'):
        result, status = get_students()
        print(json.dumps(result, indent=2, default=str))
