from flask import request, jsonify, current_app

from ..extensions import db
from ..models import Notification
from ..utils.dynamic_json import generate_user_notifications_json
from . import bp
from flask import current_app
try:
    create_access_token = None
except Exception:
    create_access_token = None
from sqlalchemy import text


def _resolve_identity():
    """Resolve current user id and role from JWT identity.

    Returns (user_id, role) where both may be None if not present.
    Accepts either a dict identity with keys like 'user_id'/'id' and 'role',
    or a raw int/str id.
    """
    # JWT identity resolution removed; always return None, None
    return None, None


@bp.route('/me/notifications', methods=['GET'])
def me_list_notifications():
    """List notifications for the current user.

    Query params:
    - unread=true  => only unread notifications
    """
    try:
        # List all notifications for all users (no auth)
        items = Notification.query.order_by(Notification.created_at.desc()).all()
        out = []
        for n in items:
            out.append({
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'category': n.category,
                'target': n.target,
                'status': n.status,
                'scheduled_at': n.scheduled_at.isoformat() if getattr(n, 'scheduled_at', None) else None,
                'created_at': n.created_at.isoformat() if getattr(n, 'created_at', None) else None
            })
        return jsonify({'success': True, 'notifications': out}), 200
    except Exception:
        current_app.logger.exception('Failed to list notifications')
        return jsonify({'success': False, 'error': 'failed to list notifications'}), 500


@bp.route('/me/notifications/<int:notification_id>', methods=['GET'])
def me_get_notification(notification_id):
    try:
        n = Notification.query.get(notification_id)
        if not n:
            return jsonify({'success': False, 'error': 'not found'}), 404
        return jsonify({'success': True, 'notification': {
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'category': n.category,
            'target': n.target,
            'status': n.status,
            'scheduled_at': n.scheduled_at.isoformat() if getattr(n, 'scheduled_at', None) else None,
            'created_at': n.created_at.isoformat() if getattr(n, 'created_at', None) else None
        }}), 200
    except Exception:
        current_app.logger.exception('Failed to get notification')
        return jsonify({'success': False, 'error': 'failed to load notification'}), 500


@bp.route('/me/notifications/<int:notification_id>/read', methods=['POST'])
def me_mark_notification_read(notification_id):
    try:
        n = Notification.query.get(notification_id)
        if not n:
            return jsonify({'success': False, 'error': 'not found'}), 404
        # No is_read column in new schema; set status to 'Read' when present
        try:
            n.status = 'Read'
        except Exception:
            pass
        db.session.commit()
        try:
            generate_user_notifications_json(None)
        except Exception:
            current_app.logger.exception('Failed to regen notifications json after mark read')
        return jsonify({'success': True}), 200
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to mark notification read')
        return jsonify({'success': False, 'error': 'failed to mark read'}), 500


@bp.route('/admin/notifications', methods=['POST'])
def admin_create_notification():
    """Create notifications for one or multiple users. Admin-only.

    Body schema examples:
    - single user: {"user_id": 3, "title": "Hi", "body": "...", "data": {}}
    - multiple users: {"user_ids": [1,2,3], "title": "Update", "body": "..."}
    """
    try:
        # Admin check removed: allow all users
        data = request.get_json(silent=True) or {}
        title = data.get('title')
        message = data.get('message')
        category = data.get('category') or 'info'
        uids = []
        if isinstance(data.get('user_ids'), list):
            try:
                uids = [int(x) for x in data.get('user_ids') if x is not None]
            except Exception:
                uids = []
        elif data.get('user_id') is not None:
            try:
                uids = [int(data.get('user_id'))]
            except Exception:
                uids = []
        if not title or not message or not uids:
            return jsonify({'success': False, 'error': 'title, message and user_id(s) required'}), 400

        created = []
        for u in uids:
            target_val = f'user:{int(u)}'
            n = Notification(title=title, message=message, category=category, target=target_val, status='Sent')
            db.session.add(n)
            created.append(u)
        db.session.commit()

        try:
            for u in created:
                try:
                    generate_user_notifications_json(int(u))
                except Exception:
                    current_app.logger.exception('Failed to regen notifications json for user %s', u)
        except Exception:
            current_app.logger.exception('Notifications JSON regeneration failed')

        return jsonify({'success': True, 'created_for': created}), 201
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to create notification')
        return jsonify({'success': False, 'error': 'failed to create notification'}), 500


@bp.route('/admin/notifications/<int:notification_id>', methods=['DELETE'])
def admin_delete_notification(notification_id):
    try:
        # Admin check removed: allow all users
        n = Notification.query.get(notification_id)
        if not n:
            return jsonify({'success': False, 'error': 'not found'}), 404

        # derive user id from target if possible
        user_of_notification = None
        try:
            if n.target and n.target.startswith('user:'):
                user_of_notification = int(n.target.split(':',1)[1])
        except Exception:
            user_of_notification = None
        db.session.delete(n)
        db.session.commit()
        try:
            if user_of_notification:
                generate_user_notifications_json(int(user_of_notification))
        except Exception:
            current_app.logger.exception('Failed to regen notifications json after delete for user %s', user_of_notification)
        return jsonify({'success': True}), 200
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to delete notification')
        return jsonify({'success': False, 'error': 'failed to delete notification'}), 500


# Debug helper: issue a test JWT with string subject for local testing only
@bp.route('/debug/jwt/<int:user_id>', methods=['GET'])
def debug_issue_jwt(user_id):
    if not (current_app.config.get('DEBUG') or current_app.config.get('ALLOW_DEBUG_ROUTES')):
        return jsonify({'success': False, 'error': 'not found'}), 404
    if not create_access_token:
        return jsonify({'success': False, 'error': 'jwt not available'}), 500
    role = request.args.get('role', 'admin')
    try:
        tok = create_access_token(identity=str(user_id), additional_claims={'role': role})
        return jsonify({'success': True, 'access_token': tok, 'user_id': user_id, 'role': role})
    except Exception:
        current_app.logger.exception('Failed to create debug jwt')
        return jsonify({'success': False, 'error': 'failed to create token'}), 500


@bp.route('/debug/notifications/align-schema', methods=['POST'])
def debug_align_notifications_schema():
    if not (current_app.config.get('DEBUG') or current_app.config.get('ALLOW_DEBUG_ROUTES')):
        return jsonify({'success': False, 'error': 'not found'}), 404
    uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if 'mysql' not in (uri or ''):
        return jsonify({'success': False, 'error': 'mysql only'}), 400
    try:
        eng = db.engine
        with eng.begin() as conn:
            # add columns if missing to match new schema
            try:
                conn.execute(text('ALTER TABLE notifications ADD COLUMN IF NOT EXISTS title VARCHAR(255) NOT NULL'))
            except Exception:
                pass
            try:
                conn.execute(text('ALTER TABLE notifications ADD COLUMN IF NOT EXISTS message TEXT NOT NULL'))
            except Exception:
                pass
            try:
                conn.execute(text('ALTER TABLE notifications ADD COLUMN IF NOT EXISTS category VARCHAR(100) NOT NULL'))
            except Exception:
                pass
            try:
                conn.execute(text('ALTER TABLE notifications ADD COLUMN IF NOT EXISTS target VARCHAR(255) NOT NULL'))
            except Exception:
                pass
            try:
                conn.execute(text('ALTER TABLE notifications ADD COLUMN IF NOT EXISTS status VARCHAR(50) NOT NULL'))
            except Exception:
                pass
            try:
                conn.execute(text('ALTER TABLE notifications ADD COLUMN IF NOT EXISTS scheduled_at DATETIME NULL'))
            except Exception:
                pass
            try:
                conn.execute(text('ALTER TABLE notifications ADD COLUMN IF NOT EXISTS created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP'))
            except Exception:
                pass
        return jsonify({'success': True}), 200
    except Exception:
        current_app.logger.exception('align-schema failed')
        return jsonify({'success': False, 'error': 'align failed'}), 500


@bp.route('/debug/notifications/seed', methods=['POST'])
def debug_seed_notifications():
    if not (current_app.config.get('DEBUG') or current_app.config.get('ALLOW_DEBUG_ROUTES')):
        return jsonify({'success': False, 'error': 'not found'}), 404
    data = request.get_json(silent=True) or {}
    uid = int(data.get('user_id') or request.args.get('user_id') or 1)
    count = int(data.get('count') or request.args.get('count') or 2)
    try:
        created = []
        for i in range(count):
            n = Notification(user_id=uid, title=f'Dummy {i+1}', body='Hello from debug seed', data={'seed': True}, is_read=False)
            db.session.add(n)
            created.append(i+1)
        db.session.commit()
        try:
            generate_user_notifications_json(int(uid))
        except Exception:
            current_app.logger.exception('Failed to regen notifications json for user %s', uid)
        return jsonify({'success': True, 'seeded': len(created)}), 201
    except Exception:
        db.session.rollback()
        current_app.logger.exception('debug seed failed')
        return jsonify({'success': False, 'error': 'seed failed'}), 500


@bp.route('/debug/notifications/seed-all', methods=['POST'])
def debug_seed_notifications_all():
    """Seed notifications table with full set of columns (legacy + new).

    Populates: title, message, category, icon, is_read, created_at, user_id, body, data
    Only fills columns that actually exist in the DB schema.
    """
    if not (current_app.config.get('DEBUG') or current_app.config.get('ALLOW_DEBUG_ROUTES')):
        return jsonify({'success': False, 'error': 'not found'}), 404
    data_in = request.get_json(silent=True) or {}
    uid = int(data_in.get('user_id') or request.args.get('user_id') or 26)
    count = int(data_in.get('count') or request.args.get('count') or 3)
    try:
        # Discover available columns on notifications
        cols = set()
        try:
            eng = db.engine
            with eng.begin() as conn:
                uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
                if 'mysql' in (uri or ''):
                    q = text("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_NAME='notifications' AND TABLE_SCHEMA = (SELECT DATABASE())")
                    rows = conn.execute(q).fetchall()
                    cols = {r[0] for r in rows}
                else:
                    # SQLite fallback
                    q = text("PRAGMA table_info(notifications)")
                    rows = conn.execute(q).fetchall()
                    # row format: cid, name, type, notnull, dflt_value, pk
                    cols = {r[1] for r in rows}
        except Exception:
            cols = set()

        inserted = 0
        with db.engine.begin() as conn:
            for i in range(count):
                title = f"Dummy Title {i+1}"
                message = f"Dummy message {i+1}"
                category = ["info","reminder","update"][i % 3]
                icon = ["🔔","📣","✅"][i % 3]
                is_read = 0
                body = f"Body copy for {i+1}"
                data_payload = {"seed": True, "n": i+1}

                # Build dynamic INSERT
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
                    col_list.append('user_id'); val_list.append(':user_id'); params['user_id'] = uid
                if 'body' in cols:
                    col_list.append('body'); val_list.append(':body'); params['body'] = body
                if 'data' in cols:
                    # store as JSON string; DB JSON/TEXT column will accept
                    import json as _json
                    col_list.append('data'); val_list.append(':data'); params['data'] = _json.dumps(data_payload)
                if 'created_at' in cols:
                    # use NOW() for MySQL; CURRENT_TIMESTAMP also works across engines
                    col_list.append('created_at'); val_list.append('CURRENT_TIMESTAMP')

                if not col_list:
                    continue
                sql = f"INSERT INTO notifications (" + ",".join(col_list) + ") VALUES (" + ",".join(val_list) + ")"
                conn.execute(text(sql), params)
                inserted += 1

        # regenerate user-specific JSON if possible
        try:
            generate_user_notifications_json(int(uid))
        except Exception:
            current_app.logger.exception('Failed to regen notifications json for user %s', uid)

        return jsonify({'success': True, 'inserted': inserted, 'user_id': uid}), 201
    except Exception:
        current_app.logger.exception('seed-all failed')
        return jsonify({'success': False, 'error': 'seed-all failed'}), 500
