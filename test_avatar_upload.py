"""Test avatar upload with a real image file"""
from app import create_app
from app.models import Student
from app.extensions import db
from PIL import Image
import io
from pathlib import Path

app = create_app()

# Create a simple test image
def create_test_image():
    """Create a simple 100x100 red square PNG"""
    img = Image.new('RGB', (100, 100), color='red')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes

with app.app_context():
    with app.test_client() as client:
        # Get first student
        student = Student.query.first()
        
        if not student:
            print("No students found. Creating a test student...")
            student = Student(
                name="Test Student",
                email="test@example.com",
                password="",
                syllabus="",
                class_="",
                subjects="Math,Science"
            )
            db.session.add(student)
            db.session.commit()
        
        print(f"\n{'='*60}")
        print(f"Testing Avatar Upload for Student ID: {student.id}")
        print(f"Name: {student.name}")
        print(f"Current avatar: {student.image or 'None'}")
        print(f"{'='*60}\n")
        
        # Create test image
        print("Creating test image (100x100 red square)...")
        test_image = create_test_image()
        
        # Upload avatar
        print(f"Uploading avatar via POST /api/v1/students/{student.id}/avatar...")
        response = client.post(
            f'/api/v1/students/{student.id}/avatar',
            data={'avatar': (test_image, 'test_avatar.png')},
            content_type='multipart/form-data'
        )
        
        print(f"Response Status: {response.status_code}")
        print(f"Response JSON: {response.get_json()}\n")
        
        if response.status_code == 200:
            # Refresh student from DB
            db.session.refresh(student)
            
            print(f"✓ Upload successful!")
            print(f"✓ Database updated: image = '{student.image}'")
            
            # Check if file exists
            upload_base = app.config.get('UPLOAD_PATH', 'uploads')
            image_path = Path(upload_base) / student.image.lstrip('/')
            
            if image_path.exists():
                file_size = image_path.stat().st_size
                print(f"✓ File saved: {image_path}")
                print(f"✓ File size: {file_size} bytes")
            else:
                print(f"✗ File NOT found at: {image_path}")
            
            # Verify via GET endpoint
            print(f"\nVerifying via GET /api/v1/students/{student.id}...")
            get_response = client.get(f'/api/v1/students/{student.id}')
            student_data = get_response.get_json()
            print(f"Student data includes image: {student_data.get('image')}")
            
            print(f"\n{'='*60}")
            print("SUCCESS! Avatar upload complete.")
            print(f"Access the avatar at: http://localhost:5000{student.image}")
            print(f"{'='*60}")
        else:
            print(f"✗ Upload failed: {response.get_json()}")
