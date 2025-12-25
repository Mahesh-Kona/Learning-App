import argparse
import json
import os
import sys
from sqlalchemy import text

# Ensure project root is on sys.path
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from app.extensions import db
from app.utils.dynamic_json import generate_user_notifications_json


def get_notification_columns(app):
    cols = set()
    try:
        with app.app_context():
            uri = app.config.get('SQLALCHEMY_DATABASE_URI', '') or ''
            eng = db.engine
            with eng.begin() as conn:
                if 'mysql' in uri:
                    q = text("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_NAME='notifications' AND TABLE_SCHEMA = (SELECT DATABASE())")
                    rows = conn.execute(q).fetchall()
                    cols = {r[0] for r in rows}
                else:
                    q = text("PRAGMA table_info(notifications)")
                    rows = conn.execute(q).fetchall()
                    # row format: cid, name, type, notnull, dflt_value, pk
                    cols = {r[1] for r in rows}
    except Exception:
        cols = set()
    return cols


def seed_notifications(app, user_id: int, count: int):
    inserted = 0
    cols = get_notification_columns(app)
    print(f"Discovered notifications columns: {sorted(list(cols))}")

    # Defaults for payloads
    titles = ["Welcome!", "Course Update", "Reminder"]
    messages = [
        "Thanks for joining the platform.",
        "A new lesson is available.",
        "Don't forget to complete your assignment.",
    ]
    categories = ["info", "update", "reminder"]
    icons = ["🔔", "📣", "✅"]

    with app.app_context():
        eng = db.engine
        with eng.begin() as conn:
            for i in range(count):
                title = titles[i % len(titles)] + f" #{i+1}"
                message = messages[i % len(messages)]
                category = categories[i % len(categories)]
                icon = icons[i % len(icons)]
                body = f"Body for notification {i+1}: {message}"
                is_read = 0
                data_payload = {"seed": True, "index": i+1}
                target = f"user:{user_id}"
                status = "new"

                col_list = []
                val_list = []
                params = {}
                if 'title' in cols:
                    col_list.append('title'); val_list.append(':title'); params['title'] = title
                if 'message' in cols:
                    col_list.append('message'); val_list.append(':message'); params['message'] = message
                if 'category' in cols:
                    col_list.append('category'); val_list.append(':category'); params['category'] = category
                if 'icon' in cols:
                    col_list.append('icon'); val_list.append(':icon'); params['icon'] = icon
                if 'is_read' in cols:
                    col_list.append('is_read'); val_list.append(':is_read'); params['is_read'] = is_read
                if 'user_id' in cols:
                    col_list.append('user_id'); val_list.append(':user_id'); params['user_id'] = user_id
                if 'target' in cols:
                    col_list.append('target'); val_list.append(':target'); params['target'] = target
                if 'status' in cols:
                    col_list.append('status'); val_list.append(':status'); params['status'] = status
                if 'body' in cols:
                    col_list.append('body'); val_list.append(':body'); params['body'] = body
                if 'data' in cols:
                    col_list.append('data'); val_list.append(':data'); params['data'] = json.dumps(data_payload)
                if 'created_at' in cols:
                    # let DB set timestamp when possible
                    col_list.append('created_at'); val_list.append('CURRENT_TIMESTAMP')
                if 'scheduled_at' in cols:
                    col_list.append('scheduled_at'); val_list.append('CURRENT_TIMESTAMP')

                if not col_list:
                    print("No insertable columns detected; skipping.")
                    break

                sql = f"INSERT INTO notifications (" + ",".join(col_list) + ") VALUES (" + ",".join(val_list) + ")"
                conn.execute(text(sql), params)
                inserted += 1

        try:
            generate_user_notifications_json(int(user_id))
        except Exception:
            # Best-effort regeneration; not fatal for seeding
            pass

    return inserted


def main():
    parser = argparse.ArgumentParser(description="Seed dummy notifications into the database.")
    parser.add_argument('--user-id', type=int, default=1, help='Target user ID to attach notifications to')
    parser.add_argument('--count', type=int, default=3, help='Number of notifications to create')
    args = parser.parse_args()

    app = create_app()
    inserted = seed_notifications(app, args.user_id, args.count)
    print(f"Inserted {inserted} notification(s) for user_id={args.user_id}.")


if __name__ == '__main__':
    main()
