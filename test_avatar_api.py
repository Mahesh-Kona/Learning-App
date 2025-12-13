"""Test avatar upload API"""
from app import create_app
from app.models import Student
from app.extensions import db

app = create_app()

with app.app_context():
    print('Testing Avatar Upload API\n')
    print('=' * 50)
    
    # Get first student
    student = Student.query.first()
    if student:
        print(f'Student ID: {student.id}')
        print(f'Name: {student.name}')
        print(f'Current image: {student.image}')
        print('\nAPI Endpoints:')
        print(f'  POST /api/v1/students/{student.id}/avatar')
        print(f'       Upload avatar (multipart/form-data with "avatar" field)')
        print(f'       Allowed: jpg, jpeg, png, gif (max 5MB)')
        print(f'  DELETE /api/v1/students/{student.id}/avatar')
        print(f'       Delete avatar')
        print('\nImages will be stored in: uploads/avatars/')
        print(f'Path format: /avatars/student_{student.id}_avatar.jpg')
    else:
        print('No students found in database')
    
    print('\n' + '=' * 50)
    print('\nExample curl command:')
    print(f'curl -X POST http://localhost:5000/api/v1/students/1/avatar \\')
    print('     -F "avatar=@path/to/image.jpg"')
