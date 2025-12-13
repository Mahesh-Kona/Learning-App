"""Add missing columns (image, mobile, status, class) to students table in SQLite"""
from app import create_app
from sqlalchemy import text, inspect
from app.extensions import db

app = create_app()

with app.app_context():
    inspector = inspect(db.engine)
    print('Database:', app.config['SQLALCHEMY_DATABASE_URI'])
    
    cols = [c['name'] for c in inspector.get_columns('students')]
    print('Current columns:', cols)
    
    # Add image column if missing
    if 'image' not in cols:
        print('\nAdding image column to students table...')
        sql = "ALTER TABLE students ADD COLUMN image VARCHAR(255)"
        db.session.execute(text(sql))
        db.session.commit()
        print('✓ Image column added successfully')
    else:
        print('\n✓ Image column already exists')
    
    # Add mobile column if missing
    if 'mobile' not in cols:
        print('\nAdding mobile column to students table...')
        sql = "ALTER TABLE students ADD COLUMN mobile VARCHAR(10)"
        db.session.execute(text(sql))
        db.session.commit()
        print('✓ Mobile column added successfully')
    else:
        print('✓ Mobile column already exists')
    
    # Add status column if missing
    if 'status' not in cols:
        print('\nAdding status column to students table...')
        sql = "ALTER TABLE students ADD COLUMN status VARCHAR(20) DEFAULT 'active'"
        db.session.execute(text(sql))
        db.session.commit()
        print('✓ Status column added successfully')
    else:
        print('✓ Status column already exists')
    
    # Add class column if missing (checking for 'class' which maps to class_)
    if 'class' not in cols:
        print('\nAdding class column to students table...')
        sql = "ALTER TABLE students ADD COLUMN class VARCHAR(50)"
        db.session.execute(text(sql))
        db.session.commit()
        print('✓ Class column added successfully')
    else:
        print('✓ Class column already exists')
    
    # Verify final state
    cols_after = [c['name'] for c in inspector.get_columns('students')]
    print('\nFinal columns:', cols_after)
    print('\n✓ All required columns are present')
