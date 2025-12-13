"""Add mobile column to students table"""
from app import create_app
from sqlalchemy import text, inspect
from app.extensions import db

app = create_app()

with app.app_context():
    inspector = inspect(db.engine)
    print('Database:', app.config['SQLALCHEMY_DATABASE_URI'])
    
    cols = [c['name'] for c in inspector.get_columns('students')]
    print('Current columns:', cols)
    
    if 'mobile' not in cols:
        print('\nAdding mobile column to students table...')
        sql = "ALTER TABLE students ADD COLUMN mobile VARCHAR(10)"
        db.session.execute(text(sql))
        db.session.commit()
        print('✓ Mobile column added successfully')
        
        # Verify
        cols_after = [c['name'] for c in inspector.get_columns('students')]
        print('Columns after:', cols_after)
    else:
        print('\n✓ Mobile column already exists')
