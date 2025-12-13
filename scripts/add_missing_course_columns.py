import sqlite3
import os

DB_PATH = os.path.join('instance', 'dev.sqlite')
# expected columns per table with SQLite-compatible types
TABLE_EXPECTED = {
    'courses': {
        'thumbnail_url': 'TEXT',
        'thumbnail_asset_id': 'INTEGER',
        'category': 'VARCHAR(100)',
        'class_name': 'VARCHAR(50)',
        'price': 'INTEGER',
        'published': 'INTEGER',
        'featured': 'INTEGER',
        'duration_weeks': 'INTEGER',
        'weekly_hours': 'INTEGER',
        'difficulty': 'VARCHAR(50)',
        'stream': 'VARCHAR(50)',
        'tags': 'TEXT'
    },
    'lessons': {
        'content_json': 'TEXT',
        'description': 'TEXT',
        'duration': 'INTEGER',
        'level': 'VARCHAR(50)',
        'objectives': 'TEXT',
        'content_version': 'INTEGER'
    }
}


def get_existing_columns(conn, table):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    rows = cur.fetchall()
    return [r[1] for r in rows]


def add_column(conn, table, name, ctype):
    cur = conn.cursor()
    print(f"Adding column {table}.{name} {ctype}")
    cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ctype}")
    conn.commit()


if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        print('DB not found:', DB_PATH)
        raise SystemExit(1)
    conn = sqlite3.connect(DB_PATH)
    for table, expected in TABLE_EXPECTED.items():
        try:
            existing = get_existing_columns(conn, table)
        except Exception as e:
            print(f'Error reading {table} table:', e)
            continue

        to_add = [(k, v) for k, v in expected.items() if k not in existing]
        if not to_add:
            print(f'No missing columns detected for {table}.')
            continue

        for name, ctype in to_add:
            try:
                add_column(conn, table, name, ctype)
            except Exception as e:
                print('Failed to add', f'{table}.{name}', '->', e)
        print('Done. Added columns for', table, ':', [n for n, _ in to_add])
    conn.close()
