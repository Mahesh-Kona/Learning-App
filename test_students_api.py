from app import create_app
from app.api.progress import get_students

app = create_app()
with app.app_context():
    with app.test_request_context('?limit=10'):
        result, status = get_students()
        print(f'Status: {status}')
        total = result.get('total')
        print(f'Total students: {total}')
        students = result.get('students', [])
        print(f'Returned: {len(students)} students')
        if students:
            first = students[0]
            print(f'First student: id={first["id"]}, name={first["name"]}, email={first["email"]}')
