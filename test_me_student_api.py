"""Test the /api/v1/me/student endpoint for student id=2"""
import os
os.environ['DATABASE_URL'] = 'mysql+pymysql://root:@localhost:3306/learning?charset=utf8mb4'
os.environ['FORCE_MYSQL'] = '1'

from app import create_app
from flask_jwt_extended import create_access_token

app = create_app()

with app.app_context():
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']
    print(f'Database: {db_uri}\n')
    
    if 'sqlite' in db_uri.lower():
        print('❌ Still using SQLite')
        exit(1)
    
    print('✅ Using MySQL/MariaDB\n')
    
    from app.models import Student, User
    from app.extensions import db
    
    student = Student.query.filter_by(id=2).first()
    if not student:
        print('❌ Student id=2 not found')
        exit(1)
    
    email = student.email
    print(f'✓ Student found:')
    print(f'  ID: {student.id}')
    print(f'  Email: {email}')
    print(f'  Name: {student.name}')
    print(f'  Mobile: {student.mobile}')
    print(f'  Class: {student.class_}')
    
    user = User.query.filter_by(email=email).first()
    if user:
        print(f'\n✓ User found: id={user.id}, role={user.role}')
    else:
        print(f'\n⚠️  No User record for {email}')
        # Create a basic user for testing
        user = User(email=email, role='student')
        user.set_password('test123')
        db.session.add(user)
        db.session.commit()
        print(f'✓ Created User: id={user.id}, password=test123')
    
    # Login via the actual login endpoint to get a valid token
    client = app.test_client()
    login_resp = client.post('/api/v1/auth/login', json={
        'email': email,
        'password': 'test123'
    })
    
    print(f'\n📤 Login Status: {login_resp.status_code}')
    if login_resp.status_code != 200:
        print(f'❌ Login failed: {login_resp.get_json()}')
        exit(1)
    
    login_data = login_resp.get_json()
    token = login_data['access_token']
    print(f'✓ Got access token from login')
    print(f'✓ JWT token created')
    
    client = app.test_client()
    payload = {
        'name': 'API Test Update',
        'mobile': '9876543210',
        'class': 'Grade 10'
    }
    print(f'\n📤 Calling PUT /api/v1/me/student')
    print(f'   Payload: {payload}')
    
    resp = client.put(
        '/api/v1/me/student',
        json=payload,
        headers={'Authorization': f'Bearer {token}'}
    )
    
    print(f'\n📊 Response Status: {resp.status_code}')
    try:
        json_resp = resp.get_json()
        print(f'📊 Response JSON: {json_resp}')
    except Exception as e:
        print(f'⚠️  Could not parse response: {e}')
        print(f'   Raw: {resp.data.decode("utf-8", errors="ignore")[:300]}')
    
    if resp.status_code == 200:
        db.session.expire(student)
        updated = Student.query.get(2)
        print(f'\n✅ Student after update:')
        print(f'   Name: {updated.name}')
        print(f'   Email: {updated.email}')
        print(f'   Mobile: {updated.mobile}')
        print(f'   Class: {updated.class_}')
        print('\n✅ API endpoint is working correctly!')
    else:
        print('\n❌ API endpoint failed')
