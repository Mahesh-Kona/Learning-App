"""Verify SQLite database schema"""
from app import create_app
from sqlalchemy import inspect
from app.extensions import db

app = create_app()

with app.app_context():
    inspector = inspect(db.engine)
    print('Database:', app.config['SQLALCHEMY_DATABASE_URI'])
    
    cols = inspector.get_columns('students')
    print('\nStudents table columns:')
    for c in cols:
        print(f"  - {c['name']}: {c['type']}")
    
    # Show a sample student
    from app.models import Student
    student = Student.query.first()
    if student:
        print(f'\nSample student:')
        print(f'  ID: {student.id}')
        print(f'  Name: {student.name}')
        print(f'  Status: {getattr(student, "status", "N/A")}')
