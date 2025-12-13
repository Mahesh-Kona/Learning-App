"""Test MariaDB connection and verify it's being used"""
import os

print("Environment variables:")
print(f"DATABASE_URL: {os.getenv('DATABASE_URL')}")

from app import create_app
from app.extensions import db
from app.models import Student

app = create_app()

with app.app_context():
    print(f"\nApp is using: {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    # Test query
    students = Student.query.all()
    print(f"\nTotal students: {len(students)}")
    print("\nStudents from database:")
    for s in students[:5]:
        print(f"  ID {s.id}: {s.name} - status: {getattr(s, 'status', 'N/A')}")
