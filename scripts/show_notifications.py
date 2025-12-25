from sqlalchemy import text
import os
import sys

CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from app.extensions import db


def main():
    app = create_app()
    with app.app_context():
        eng = db.engine
        with eng.begin() as conn:
            # list columns
            uri = app.config.get('SQLALCHEMY_DATABASE_URI', '') or ''
            cols = []
            if 'mysql' in uri:
                rows = conn.execute(text("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_NAME='notifications' AND TABLE_SCHEMA = (SELECT DATABASE()) ORDER BY ORDINAL_POSITION"))
                cols = [r[0] for r in rows]
            else:
                rows = conn.execute(text("PRAGMA table_info(notifications)")).fetchall()
                cols = [r[1] for r in rows]
            print("Columns:", cols)

            # show recent rows
            try:
                rows = conn.execute(text("SELECT * FROM notifications ORDER BY created_at DESC LIMIT 10")).fetchall()
            except Exception:
                rows = conn.execute(text("SELECT * FROM notifications ORDER BY id DESC LIMIT 10")).fetchall()
            for r in rows:
                print(dict(r._mapping))


if __name__ == '__main__':
    main()
