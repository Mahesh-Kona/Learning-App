from flask import Blueprint, render_template, render_template_string, request, redirect, url_for, session, flash, current_app, send_from_directory
from app.extensions import db
from app.models import User
from app.models import Course, Lesson, Topic, Asset
from werkzeug.utils import secure_filename
import uuid
import json
import os
from types import SimpleNamespace
from datetime import datetime
import traceback


admin_bp = Blueprint('admin_bp', __name__, url_prefix='/admin')


@admin_bp.route('/login', methods=['GET'])
def admin_login_get():
    # Render the admin login page
    # Render the main index page which contains the login form. User requested only index.html remain.
    return render_template('index.html')


@admin_bp.route('/login', methods=['POST'])
def admin_login_post():
    # Simple session-based admin login for the admin UI
    email = request.form.get('email') or request.form.get('username')
    password = request.form.get('password')
    if not email or not password:
        flash('Missing credentials', 'error')
        return redirect(url_for('admin_bp.admin_login_get'))

    # detect XHR callers so we can return JSON for AJAX logins
    is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # Development fallback: allow a quick dev admin login so the dashboard can be reached
    # Use credentials admin/admin OR enable DEV_FORCE_ADMIN=1 in environment to allow access.
    dev_force = os.environ.get('DEV_FORCE_ADMIN') == '1'
    if (email == 'admin' and password == 'admin') or dev_force:
        # honor "remember me" flag if provided (form or JSON)
        remember_raw = None
        try:
            remember_raw = request.form.get('remember')
        except Exception:
            remember_raw = None
        if not remember_raw:
            try:
                data = request.get_json(silent=True) or {}
                remember_raw = data.get('remember')
            except Exception:
                remember_raw = None

        remember = False
        if isinstance(remember_raw, str):
            remember = remember_raw.lower() in ('1', 'true', 'on', 'yes')
        elif isinstance(remember_raw, (int, bool)):
            remember = bool(remember_raw)

        # set session permanence before creating session values
        session.permanent = bool(remember)
        session['admin_user_id'] = 'dev_admin'
        if not is_xhr:
            flash('Welcome, dev admin!', 'success')
        if is_xhr:
            # include cookie expiry when remember is requested so client can confirm persistence
            expires = None
            try:
                if session.permanent:
                    lifetime = current_app.permanent_session_lifetime
                    expires = (datetime.utcnow() + lifetime).isoformat() if lifetime else None
            except Exception:
                expires = None
            payload = {"success": True, "redirect": url_for('admin_bp.admin_dashboard')}
            if expires:
                payload['expires'] = expires
            return payload, 200
        return redirect(url_for('admin_bp.admin_dashboard'))

    # Otherwise, attempt to authenticate against the DB.
    try:
        user = User.query.filter_by(email=email).first()
    except Exception as e:
        # If DB access fails, provide a clear flash message and offer dev fallback instructions
        current_app.logger.exception('Database error during admin login')
        msg = 'Database error. If you are developing locally, you can login with admin/admin or set DEV_FORCE_ADMIN=1.'
        if is_xhr:
            return {"success": False, "error": msg}, 500
        flash(msg, 'error')
        return redirect(url_for('admin_bp.admin_login_get'))

    # If standard DB user exists and is admin, use that.
    if user and user.check_password(password) and user.role == 'admin':
        # honor remember flag for regular users as well
        remember_raw = None
        try:
            remember_raw = request.form.get('remember')
        except Exception:
            remember_raw = None
        if not remember_raw:
            try:
                data = request.get_json(silent=True) or {}
                remember_raw = data.get('remember')
            except Exception:
                remember_raw = None

        remember = False
        if isinstance(remember_raw, str):
            remember = remember_raw.lower() in ('1', 'true', 'on', 'yes')
        elif isinstance(remember_raw, (int, bool)):
            remember = bool(remember_raw)

        session.permanent = bool(remember)
        session['admin_user_id'] = user.id
        if is_xhr:
            expires = None
            try:
                if session.permanent:
                    lifetime = current_app.permanent_session_lifetime
                    expires = (datetime.utcnow() + lifetime).isoformat() if lifetime else None
            except Exception:
                expires = None
            payload = {"success": True, "redirect": url_for('admin_bp.admin_dashboard')}
            if expires:
                payload['expires'] = expires
            return payload, 200
        flash('Welcome, admin!', 'success')
        return redirect(url_for('admin_bp.admin_dashboard'))

    # otherwise invalid
    msg = 'Invalid admin credentials'
    if is_xhr:
        return {"success": False, "error": msg}, 401
    flash(msg, 'error')
    return redirect(url_for('admin_bp.admin_login_get'))


@admin_bp.route('/dashboard')
def admin_dashboard():
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))

    # Support dev admin sentinel value — create a lightweight user-like object for templates
    if uid == 'dev_admin':
        user = SimpleNamespace(id='dev_admin', role='admin', name='Dev Admin', email='dev@local')
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return redirect(url_for('admin_bp.admin_login_get'))

    # Prefer the packaged `dashboard.html`. If rendering fails (missing or broken),
    # try the project-level `templates/dashboard.html` and finally show the
    # admin_dashboard_missing fallback.
    try:
        return render_template('dashboard.html', user=user, active='dashboard')
    except Exception:
        project_root = os.path.abspath(os.path.join(current_app.root_path, '..'))
        candidate = os.path.join(project_root, 'templates', 'dashboard.html')
        if os.path.exists(candidate):
            try:
                with open(candidate, 'r', encoding='utf8') as fh:
                    content = fh.read()
                return render_template_string(content, user=user, active='dashboard')
            except Exception:
                current_app.logger.exception('Failed to render project-level dashboard.html')
        # final fallback
        return render_template('admin_dashboard_missing.html', user=user, active='dashboard')


@admin_bp.route('/create_course', methods=['GET'])
def create_course_page():
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))
    # simple access allowed for dev_admin sentinel as well
    if uid == 'dev_admin':
        user = SimpleNamespace(id='dev_admin', role='admin', name='Dev Admin', email='dev@local')
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return redirect(url_for('admin_bp.admin_login_get'))
    return render_template('create_course.html', user=user, active='create_course')


@admin_bp.route('/create_topic', methods=['GET'])
def create_topic_page():
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))
    if uid == 'dev_admin':
        user = SimpleNamespace(id='dev_admin', role='admin', name='Dev Admin', email='dev@local')
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return redirect(url_for('admin_bp.admin_login_get'))
    # Provide an optional lesson selector so the admin can attach the topic to a lesson.
    selected_lesson = request.args.get('lesson_id')
    try:
        lessons = Lesson.query.order_by(Lesson.created_at.desc()).all()
    except Exception:
        lessons = []
    return render_template('create_topic.html', user=user, active='create_topic', lessons=lessons, selected_lesson=selected_lesson)


@admin_bp.route('/all_courses', methods=['GET'])
def all_courses_page():
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))
    if uid == 'dev_admin':
        user = SimpleNamespace(id='dev_admin', role='admin', name='Dev Admin', email='dev@local')
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return redirect(url_for('admin_bp.admin_login_get'))

    try:
        courses_q = Course.query.order_by(Course.title).all()
        courses = []
        for c in courses_q:
            try:
                lessons_count = c.lessons.count() if hasattr(c, 'lessons') else Lesson.query.filter_by(course_id=c.id).count()
            except Exception:
                lessons_count = 0
            courses.append({
                'id': c.id,
                'name': c.title,
                'code': f'COURSE{c.id}',
                'description': c.description or '',
                'duration': None,
                'level': c.difficulty or '',
                'lessons': lessons_count
            })
    except Exception:
        courses = []

    return render_template('all-courses.html', user=user, active='all_courses', courses=courses)


@admin_bp.route('/category-management', methods=['GET'])
def category_management():
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))
    if uid == 'dev_admin':
        user = SimpleNamespace(id='dev_admin', role='admin', name='Dev Admin', email='dev@local')
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return redirect(url_for('admin_bp.admin_login_get'))

    # Render the category management template. Template will include sidebar and handle content.
    return render_template('category-management.html', user=user, active='categories')


@admin_bp.route('/all_topics', methods=['GET'])
def all_topics_page():
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))
    if uid == 'dev_admin':
        user = SimpleNamespace(id='dev_admin', role='admin', name='Dev Admin', email='dev@local')
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return redirect(url_for('admin_bp.admin_login_get'))

    try:
        topics_q = Topic.query.order_by(Topic.created_at.desc()).all()
        topics = []
        lesson_cache = {}
        for t in topics_q:
            data = t.data_json or {}
            # resolve lesson title
            lid = t.lesson_id
            lesson_title = ''
            try:
                if lid in lesson_cache:
                    lesson_title = lesson_cache[lid]
                else:
                    l = Lesson.query.get(lid)
                    lesson_title = l.title if l else ''
                    lesson_cache[lid] = lesson_title
            except Exception:
                lesson_title = ''

            topics.append({
                'id': t.id,
                'name': t.title or '',
                'lesson': lesson_title,
                'lesson_id': lid,
                'description': data.get('description') if isinstance(data, dict) else '',
                'duration': data.get('duration') if isinstance(data, dict) else None,
                'estimated_time': data.get('estimated_time') if isinstance(data, dict) else data.get('estimatedTime') if isinstance(data, dict) else None,
                'difficulty': data.get('difficulty') if isinstance(data, dict) else None,
                'type': data.get('type') if isinstance(data, dict) else None,
                'order': data.get('order') if isinstance(data, dict) else None
            })
    except Exception:
        topics = []
    # Also provide a lessons list for the lesson filter (id + name)
    try:
        lessons_q = Lesson.query.order_by(Lesson.title).all()
        lessons = [{'id': l.id, 'name': l.title or ''} for l in lessons_q]
    except Exception:
        lessons = []

    return render_template('all-topics.html', user=user, active='all_topics', topics=topics, lessons=lessons)


@admin_bp.route('/delete_course', methods=['POST', 'DELETE'])
def delete_course():
    """Delete a course by id. Accepts query param `id` or JSON body {id: ...}.
    Returns JSON for XHR or redirects back to All Courses page for normal requests.
    """
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))

    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return redirect(url_for('admin_bp.admin_login_get'))

    cid = request.args.get('id')
    if not cid:
        try:
            data = request.get_json(silent=True) or {}
            cid = data.get('id')
        except Exception:
            cid = None

    try:
        cid = int(cid)
    except Exception:
        cid = None

    if not cid:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "missing or invalid id"}, 400
        flash('Missing course id for deletion', 'error')
        return redirect(url_for('admin_bp.all_courses_page'))

    try:
        course = Course.query.get(cid)
        if not course:
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return {"success": False, "error": "course not found"}, 404
            flash('Course not found', 'error')
            return redirect(url_for('admin_bp.all_courses_page'))

        # Optionally: handle cascade of lessons/assets if not handled by DB foreign keys
        db.session.delete(course)
        db.session.commit()
    except Exception:
        current_app.logger.exception('Failed to delete course %s', cid)
        try:
            db.session.rollback()
        except Exception:
            current_app.logger.exception('rollback failed after delete failure')
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "failed to delete course"}, 500
        flash('Failed to delete course', 'error')
        return redirect(url_for('admin_bp.all_courses_page'))

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return {"success": True, "id": cid}, 200

    flash('Course deleted', 'success')
    return redirect(url_for('admin_bp.all_courses_page'))


@admin_bp.route('/create_topic', methods=['POST'])
def create_topic_post():
    """Create a topic from the admin UI. Accepts JSON or form data.
    Expected fields: title, lesson_id (required), data_json (optional as JSON string) or objectives/cards parsed from form.
    Returns JSON for XHR or redirects back to lesson page.
    """
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))

    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return redirect(url_for('admin_bp.admin_login_get'))

    data = request.get_json(silent=True) or request.form or {}
    title = data.get('title') or data.get('topicTitle')
    lesson_id = data.get('lesson_id') or data.get('lessonId') or request.args.get('lesson_id')

    if not title or not lesson_id:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "missing title or lesson_id"}, 400
        flash('Missing topic title or lesson selection', 'error')
        return redirect(url_for('admin_bp.create_topic_page'))

    # Build a content payload to store in Topic.data_json from any provided fields
    data_json = None
    # If caller supplied an explicit data_json field (string or object), try to use it
    raw = data.get('data_json') or data.get('dataJson')
    if raw:
        try:
            data_json = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            # leave as raw string fallback
            data_json = raw
        # If a dict was supplied, merge optional metadata fields if present
        try:
            if isinstance(data_json, dict):
                # prefer explicit keys from JSON payload, else look in top-level data/form
                est = None
                diff = None
                if isinstance(data, dict):
                    est = data.get('estimated_time') or data.get('estimatedTime')
                    diff = data.get('difficulty') or data.get('topicDifficulty') or data.get('topic_difficulty')
                try:
                    if hasattr(request, 'form') and request.form:
                        est = est or request.form.get('estimated_time') or request.form.get('estimatedTime')
                        diff = diff or request.form.get('difficulty') or request.form.get('topicDifficulty')
                except Exception:
                    pass

                if est is not None and est != '':
                    try:
                        data_json['estimated_time'] = int(est)
                    except Exception:
                        data_json['estimated_time'] = est
                if diff:
                    data_json['difficulty'] = diff
        except Exception:
            # merging metadata should not block topic creation
            current_app.logger.exception('Failed to merge metadata into provided data_json')
    else:
        # Try to assemble from common fields: description, objectives, cards
        description = None
        objectives = None
        cards = None
        estimated_time = None
        difficulty = None

        # JSON request body case: data is already a dict
        if isinstance(data, dict):
            description = data.get('description') or data.get('topicDescription')
            objectives = data.get('objectives')
            cards = data.get('cards')
            # capture optional metadata fields from JSON
            estimated_time = data.get('estimated_time') or data.get('estimatedTime')
            difficulty = data.get('difficulty') or data.get('topicDifficulty')

        # Form-encoded case: use getlist for repeated fields or named inputs
        try:
            if hasattr(request.form, 'getlist') and request.form:
                # description from form
                description = description or request.form.get('description') or request.form.get('topicDescription')
                # objectives may come as multiple fields named objectives[] or objectives
                objs = request.form.getlist('objectives') or request.form.getlist('objectives[]')
                if objs:
                    objectives = objs
                # cards may be provided as a JSON string in 'cards'
                raw_cards = request.form.get('cards')
                if raw_cards:
                    try:
                        cards = json.loads(raw_cards)
                    except Exception:
                        cards = raw_cards
                # metadata fields
                estimated_time = estimated_time or request.form.get('estimated_time') or request.form.get('estimatedTime')
                difficulty = difficulty or request.form.get('difficulty') or request.form.get('topicDifficulty')
        except Exception:
            pass

        payload = {}
        if description:
            payload['description'] = description
        if objectives:
            payload['objectives'] = objectives
        if cards:
            payload['cards'] = cards
        if estimated_time is not None and estimated_time != '':
            # try to coerce to int when possible
            try:
                payload['estimated_time'] = int(estimated_time)
            except Exception:
                payload['estimated_time'] = estimated_time
        if difficulty:
            payload['difficulty'] = difficulty

        # If the incoming JSON included additional keys besides title/lesson_id, merge them too
        if isinstance(data, dict):
            for k, v in data.items():
                if k in ('title', 'lesson_id', 'lessonId', 'data_json', 'dataJson'):
                    continue
                # avoid overwriting explicit payload fields
                if k in payload:
                    continue
                payload[k] = v

        if payload:
            data_json = payload

    try:
        # ensure lesson exists
        lesson = Lesson.query.get(int(lesson_id))
        if not lesson:
            raise ValueError('lesson not found')

        topic = Topic(lesson_id=lesson.id, title=title.strip(), data_json=data_json)
        db.session.add(topic)
        db.session.commit()
    except Exception:
        current_app.logger.exception('Failed to create topic')
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "failed to create topic"}, 500
        flash('Failed to create topic', 'error')
        return redirect(url_for('admin_bp.create_topic_page'))

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return {"success": True, "id": topic.id}, 201

    # Redirect back to lesson page so admin can see the topic listed
    return redirect(url_for('admin_bp.lesson_page') + f'?lesson_id={topic.lesson_id}')


@admin_bp.route('/get_topic', methods=['GET'])
def get_topic():
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))
    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return redirect(url_for('admin_bp.admin_login_get'))

    tid = request.args.get('id')
    try:
        tid = int(tid)
    except Exception:
        tid = None

    if not tid:
        return {"success": False, "error": "missing or invalid id"}, 400

    try:
        topic = Topic.query.get(tid)
        if not topic:
            return {"success": False, "error": "topic not found"}, 404

        data = topic.data_json if isinstance(topic.data_json, dict) else (topic.data_json or {})
        payload = {
            'id': topic.id,
            'title': topic.title,
            'lesson_id': topic.lesson_id,
            'description': data.get('description') if isinstance(data, dict) else '',
            'duration': data.get('duration') if isinstance(data, dict) else None,
            'estimated_time': data.get('estimated_time') if isinstance(data, dict) else data.get('estimatedTime') if isinstance(data, dict) else None,
            'difficulty': data.get('difficulty') if isinstance(data, dict) else None,
            'type': data.get('type') if isinstance(data, dict) else None,
            'order': data.get('order') if isinstance(data, dict) else None
        }
        return {"success": True, "topic": payload}, 200
    except Exception:
        current_app.logger.exception('Failed to load topic %s', tid)
        return {"success": False, "error": "failed to load topic"}, 500


@admin_bp.route('/update_topic', methods=['POST'])
def update_topic():
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))
    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return redirect(url_for('admin_bp.admin_login_get'))

    data = request.get_json(silent=True) or {}
    tid = data.get('id')
    try:
        tid = int(tid)
    except Exception:
        tid = None

    if not tid:
        return {"success": False, "error": "missing or invalid id"}, 400

    try:
        topic = Topic.query.get(tid)
        if not topic:
            return {"success": False, "error": "topic not found"}, 404

        # update title if provided
        title = data.get('title')
        if title is not None:
            topic.title = title.strip()

        # update data_json fields (description, estimated_time, duration, difficulty, type, order)
        existing = topic.data_json if isinstance(topic.data_json, dict) else (topic.data_json or {})
        if not isinstance(existing, dict):
            existing = {}

        for key in ('description', 'estimated_time', 'duration', 'difficulty', 'type', 'order'):
            if key in data:
                existing[key] = data.get(key)

        topic.data_json = existing

        db.session.add(topic)
        db.session.commit()

        return {"success": True, "topic": {'id': topic.id, 'title': topic.title, 'data_json': topic.data_json}}, 200
    except Exception:
        current_app.logger.exception('Failed to update topic %s', tid)
        try:
            db.session.rollback()
        except Exception:
            current_app.logger.exception('rollback failed after topic update failure')
        return {"success": False, "error": "failed to update topic"}, 500


@admin_bp.route('/delete_topic', methods=['POST', 'DELETE'])
def delete_topic():
    """Delete a topic by id. Accepts query param `id` or JSON body {id: ...}.
    Returns JSON for XHR or redirects back to All Topics page for normal requests.
    """
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))

    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return redirect(url_for('admin_bp.admin_login_get'))

    # id can come from query string or JSON body
    tid = request.args.get('id')
    if not tid:
        try:
            data = request.get_json(silent=True) or {}
            tid = data.get('id')
        except Exception:
            tid = None

    try:
        tid = int(tid)
    except Exception:
        tid = None

    if not tid:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "missing or invalid id"}, 400
        flash('Missing topic id for deletion', 'error')
        return redirect(url_for('admin_bp.all_topics_page'))

    try:
        topic = Topic.query.get(tid)
        if not topic:
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return {"success": False, "error": "topic not found"}, 404
            flash('Topic not found', 'error')
            return redirect(url_for('admin_bp.all_topics_page'))

        db.session.delete(topic)
        db.session.commit()
    except Exception:
        current_app.logger.exception('Failed to delete topic %s', tid)
        try:
            db.session.rollback()
        except Exception:
            current_app.logger.exception('rollback failed after delete failure')
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "failed to delete topic"}, 500
        flash('Failed to delete topic', 'error')
        return redirect(url_for('admin_bp.all_topics_page'))

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return {"success": True, "id": tid}, 200

    flash('Topic deleted', 'success')
    return redirect(url_for('admin_bp.all_topics_page'))


# Serve the topic-editor React app (best-effort). This will serve files from the
# repository's topic-editor/topic-editor folder. If the React app is built into
# a `dist`/`build` folder or uses absolute paths, you may need to build/copy the
# production assets into that folder or run the dev server separately.
@admin_bp.route('/topic-editor/')
@admin_bp.route('/topic-editor/<path:filename>')
def serve_topic_editor(filename='index.html'):
    # project root is one level up from app package dir
    project_root = os.path.abspath(os.path.join(current_app.root_path, '..'))
    editor_dir = os.path.join(project_root, 'topic-editor', 'topic-editor')
    if not os.path.exists(editor_dir):
        # If the editor isn't present, redirect back to dashboard so the admin isn't left on a 404
        return redirect(url_for('admin_bp.admin_dashboard'))
    # send the requested file (index.html by default)
    return send_from_directory(editor_dir, filename)


@admin_bp.route('/create_course', methods=['POST'])
def create_course_post():
    """Accept form submission to create a Course (admin UI).
    Returns JSON when called via fetch, or redirects back to dashboard on plain form submit.
    """
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))

    # admin check / dev_admin allowed
    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return redirect(url_for('admin_bp.admin_login_get'))

    # Read form fields
    title = request.form.get('title') or request.form.get('courseTitle')
    description = request.form.get('description') or request.form.get('courseDescription')
    # optional metadata fields
    category = request.form.get('category') or request.form.get('courseCategory')
    class_name = request.form.get('class') or request.form.get('courseClass')
    price = request.form.get('price') or request.form.get('coursePrice')
    duration_weeks = request.form.get('duration') or request.form.get('courseDuration')
    weekly_hours = request.form.get('weekly_hours') or request.form.get('weeklyHours')
    difficulty = request.form.get('difficulty')
    stream = request.form.get('stream') or request.form.get('courseStream')
    # booleans and tags
    published_raw = request.form.get('published')
    featured_raw = request.form.get('featured')
    tags_raw = request.form.get('tags') or request.form.get('courseTags')
    # normalize booleans (checkboxes submit 'on' when checked)
    def _to_bool(val):
        if val is None:
            return False
        if isinstance(val, bool):
            return val
        return str(val).lower() in ('1', 'true', 'on', 'yes')
    published = _to_bool(published_raw)
    featured = _to_bool(featured_raw)

    if not title:
        # If called via browser form submit, flash and redirect
        flash('Course title is required', 'error')
        return redirect(url_for('admin_bp.create_course_page'))

    # Persist the course first to avoid session rollback when asset creation fails
    try:
        course = Course(
            title=title.strip(),
            description=(description or '').strip(),
            category=(category or None),
            class_name=(class_name or None),
            price=(int(price) if price else None),
                duration_weeks=(int(duration_weeks) if duration_weeks else None),
                weekly_hours=(int(weekly_hours) if weekly_hours else None),
                difficulty=(difficulty or None),
                stream=(stream or None),
                tags=(tags_raw.strip() if isinstance(tags_raw, str) and tags_raw.strip() else None),
                published=published,
                featured=featured
        )
        db.session.add(course)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        # handle optional thumbnail upload separately so failures don't break the course insert
        try:
            if 'thumbnail' in request.files and request.files['thumbnail'].filename:
                f = request.files['thumbnail']
                orig_name = secure_filename(f.filename)
                unique_name = f"{uuid.uuid4().hex}_{orig_name}"
                UP = current_app.config.get('UPLOAD_PATH', '/tmp/uploads')
                if not os.path.isabs(UP):
                    UP = os.path.join(current_app.root_path, UP)
                os.makedirs(UP, exist_ok=True)
                filepath = os.path.join(UP, unique_name)
                f.save(filepath)
                url = f"/uploads/{unique_name}"

                # create Asset in its own transaction
                try:
                    asset = Asset(url=url, uploader_id=None, size=os.path.getsize(filepath), mime_type=f.mimetype)
                    db.session.add(asset)
                    db.session.commit()
                except Exception:
                    # Attempt robust fallback: rollback and try a raw INSERT then lookup the inserted row by URL
                    try:
                        db.session.rollback()
                    except Exception:
                        current_app.logger.exception('rollback failed after asset create failure')
                    current_app.logger.exception('Failed to create Asset row for course thumbnail, attempting fallback insert')
                    try:
                        from sqlalchemy import text
                        engine = db.get_engine(current_app)
                        dialect = engine.dialect.name
                        tsfn = 'NOW()' if dialect not in ('sqlite',) else "CURRENT_TIMESTAMP"
                        sql = text(f'INSERT INTO assets (url, size, mime_type, created_at) VALUES (:url, :size, :mime_type, {tsfn})')
                        with engine.begin() as conn:
                            conn.execute(sql, {'url': url, 'size': os.path.getsize(filepath), 'mime_type': f.mimetype})
                        # attempt to load the new asset by URL
                        asset = Asset.query.filter_by(url=url).order_by(Asset.created_at.desc()).first()
                        if not asset:
                            current_app.logger.warning('Fallback insert succeeded but asset not found via query')
                    except Exception:
                        current_app.logger.exception('Fallback asset insert also failed')

                # If an asset object exists (either created normally or via fallback), attach it to the course
                if 'asset' in locals() and asset is not None:
                    try:
                        db.session.add(course)
                        course.thumbnail_url = url
                        if hasattr(course, 'thumbnail_asset_id') and getattr(asset, 'id', None):
                            course.thumbnail_asset_id = asset.id
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                        current_app.logger.exception('Failed to attach asset to course')
        except Exception:
            current_app.logger.exception('Failed handling thumbnail upload')

        # If the client already uploaded the thumbnail via the uploads API and
        # provided `thumbnail_asset_id` / `thumbnail_url` in the form, attach
        # those values to the course as well. This supports the client flow
        # where the file is POSTed to /api/v1/uploads first.
        try:
            form_asset_id = request.form.get('thumbnail_asset_id') or request.form.get('thumbnailAssetId')
            form_thumbnail_url = request.form.get('thumbnail_url') or request.form.get('thumbnailUrl') or request.form.get('thumbnailURL')
            if form_asset_id or form_thumbnail_url:
                try:
                    if form_thumbnail_url:
                        course.thumbnail_url = form_thumbnail_url
                    if form_asset_id:
                        try:
                            aid = int(form_asset_id)
                            a = Asset.query.get(aid)
                            if a:
                                course.thumbnail_asset_id = aid
                            else:
                                current_app.logger.warning('Provided thumbnail_asset_id not found: %s', aid)
                        except Exception:
                            current_app.logger.exception('Invalid thumbnail_asset_id provided')
                    db.session.add(course)
                    db.session.commit()
                except Exception:
                    try:
                        db.session.rollback()
                    except Exception:
                        current_app.logger.exception('rollback failed while attaching provided asset')
                    current_app.logger.exception('Failed to attach provided thumbnail fields to course')
        except Exception:
            current_app.logger.exception('Error processing thumbnail_asset_id/thumbnail_url from form')
    except Exception as e:
        # Log full exception stack for server logs
        current_app.logger.exception('Failed to create course')
        # Also persist the traceback to a file in instance/logs for easier retrieval
        try:
            logs_dir = os.path.join(current_app.instance_path, 'logs')
            os.makedirs(logs_dir, exist_ok=True)
            fp = os.path.join(logs_dir, 'create_course_errors.log')
            with open(fp, 'a', encoding='utf8') as fh:
                fh.write('---\n')
                fh.write(datetime.utcnow().isoformat() + '\n')
                fh.write(traceback.format_exc())
                fh.write('\n')
        except Exception:
            current_app.logger.exception('Failed to write create_course error log')
        # If caller expects JSON/XHR return a JSON error. In debug mode include the exception message
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept', '').startswith('application/json'):
            if current_app.debug:
                # Safe to include error details in debug/dev mode to aid debugging
                return {"success": False, "error": f"failed to create course: {str(e)}"}, 500
            return {"success": False, "error": "failed to create course"}, 500
        # For non-JSON callers fall back to a flash and redirect
        flash('Failed to create course', 'error')
        return redirect(url_for('admin_bp.create_course_page'))

@admin_bp.route('/update_course', methods=['POST'])
def update_course():
    """Update an existing course. Accepts JSON or form data.
    Expects: id (required), title/name, description, duration (optional), level (difficulty), and other optional fields.
    Returns JSON for XHR callers.
    """
    # detect XHR callers
    is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json or request.headers.get('Accept', '').startswith('application/json')

    uid = session.get('admin_user_id')
    if not uid:
        if is_xhr:
            return {"success": False, "error": "not authenticated"}, 401
        return redirect(url_for('admin_bp.admin_login_get'))

    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            if is_xhr:
                return {"success": False, "error": "not authorized"}, 403
            return redirect(url_for('admin_bp.admin_login_get'))

    data = request.get_json(silent=True) or request.form or {}
    cid = data.get('id') or request.args.get('id')
    if not cid:
        if is_xhr:
            return {"success": False, "error": "missing course id"}, 400
        return redirect(url_for('admin_bp.all_courses_page'))

    try:
        cid = int(cid)
    except Exception:
        if is_xhr:
            return {"success": False, "error": "invalid course id"}, 400
        return redirect(url_for('admin_bp.all_courses_page'))

    try:
        course = Course.query.get(cid)
        if not course:
            if is_xhr:
                return {"success": False, "error": "course not found"}, 404
            flash('Course not found', 'error')
            return redirect(url_for('admin_bp.all_courses_page'))

        # Map incoming fields to model columns (be permissive)
        title = data.get('title') or data.get('name') or data.get('courseName')
        description = data.get('description') or data.get('courseDescription')
        duration = data.get('duration')
        level = data.get('level') or data.get('difficulty')
        lessons = data.get('lessons')

        if title is not None:
            course.title = str(title).strip()
        if description is not None:
            course.description = description
        if level is not None:
            if level in ('beginner', 'intermediate', 'advanced'):
                course.difficulty = level
            else:
                course.difficulty = None
        if duration is not None and duration != '':
            try:
                course.duration_weeks = int(duration)
            except Exception:
                pass

        db.session.add(course)
        db.session.commit()

        # return the updated representation used by the UI
        lessons_count = course.lessons.count() if hasattr(course, 'lessons') else (int(lessons) if lessons else 0)
        payload = {
            'success': True,
            'id': course.id,
            'name': course.title,
            'code': f'COURSE{course.id}',
            'description': course.description or '',
            'duration': course.duration_weeks,
            'level': course.difficulty or '',
            'lessons': lessons_count
        }
        return payload, 200
    except Exception:
        current_app.logger.exception('Failed to update course %s', cid)
        try:
            db.session.rollback()
        except Exception:
            current_app.logger.exception('rollback failed after update failure')
        if is_xhr:
            return {"success": False, "error": "failed to update course"}, 500
        flash('Failed to update course', 'error')
        return redirect(url_for('admin_bp.all_courses_page'))


@admin_bp.route('/lesson', methods=['GET'])
def lesson_page():
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))
    if uid == 'dev_admin':
        user = SimpleNamespace(id='dev_admin', role='admin', name='Dev Admin', email='dev@local')
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return redirect(url_for('admin_bp.admin_login_get'))
    # Provide courses and categories to the lesson template so the client
    # can populate the course selector without hard-coded sample data.
    try:
        # Courses
        courses_q = Course.query.order_by(Course.title).all()
        courses = [
            {
                'id': c.id,
                'name': c.title,
                'category': c.category or '',
                'class_name': c.class_name or ''
            }
            for c in courses_q
        ]

        # extract distinct categories (preserve ordering)
        seen = set()
        categories = []
        for c in courses:
            cat = c.get('category') or ''
            if cat and cat not in seen:
                seen.add(cat)
                categories.append({'name': cat})

        # Lessons
        lessons_q = Lesson.query.order_by(Lesson.created_at.desc()).all()
        lessons = [
            {
                'id': l.id,
                'courseId': l.course_id,
                'title': l.title,
                'description': l.description,
                'duration': l.duration,
                'level': l.level,
                'objectives': l.objectives
            }
            for l in lessons_q
        ]

        # Topics
        topics_q = Topic.query.order_by(Topic.created_at.asc()).all()
        topics = []
        for t in topics_q:
            data = t.data_json or {}
            topic_obj = {
                'id': t.id,
                'lessonId': t.lesson_id,
                'title': t.title,
                'type': None,
                'content': None
            }
            if isinstance(data, dict):
                topic_obj['type'] = data.get('type')
                topic_obj['content'] = data.get('content')
            topics.append(topic_obj)

    except Exception:
        courses = []
        categories = []
        lessons = []
        topics = []

    return render_template('lesson.html', user=user, active='lesson', courses=courses, categories=categories, lessons=lessons, topics=topics)


@admin_bp.route('/course_lessons', methods=['GET'])
def course_lessons():
    """Return JSON list of lessons for a given course id.
    Query param: id (course id)
    Returns: { success: True, lessons: [ {id, title, description, duration, level} ] }
    """
    uid = session.get('admin_user_id')
    if not uid:
        return {"success": False, "error": "not authenticated"}, 401

    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return {"success": False, "error": "not authorized"}, 403

    cid = request.args.get('id') or request.args.get('course_id')
    try:
        cid = int(cid)
    except Exception:
        return {"success": False, "error": "invalid course id"}, 400

    try:
        lessons_q = Lesson.query.filter_by(course_id=cid).order_by(Lesson.created_at.desc()).all()
        lessons_list = [
            {
                'id': l.id,
                'title': l.title,
                'description': l.description or '',
                'duration': l.duration,
                'level': l.level or ''
            }
            for l in lessons_q
        ]
        return {"success": True, "lessons": lessons_list}, 200
    except Exception:
        current_app.logger.exception('Failed to load lessons for course %s', cid)
        return {"success": False, "error": "failed to load lessons"}, 500


@admin_bp.route('/create_lesson', methods=['POST'])
def create_lesson_post():
    """Create a lesson from the admin UI. Accepts form or JSON with title and course_id.
    Returns JSON for XHR or redirects back to lesson page.
    """
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))

    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return redirect(url_for('admin_bp.admin_login_get'))

    # support both JSON and form submission
    data = request.get_json(silent=True) or request.form or {}
    title = data.get('title') or data.get('lessonTitle')
    course_id = data.get('course_id') or data.get('courseId') or request.args.get('course_id')

    # optional lesson metadata
    description = data.get('description') or data.get('lessonDescription')
    duration = data.get('duration') or data.get('lessonDuration')
    level = data.get('level') or data.get('lessonLevel')
    objectives = data.get('objectives') or data.get('lessonObjectives')

    if not title or not course_id:
        flash('Missing title or course_id for lesson creation', 'error')
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "missing title or course_id"}, 400
        return redirect(url_for('admin_bp.lesson_page'))

    try:
        # Package optional metadata into content_json so existing schema is unchanged
        content = {}
        if description:
            content['description'] = description
        if duration:
            try:
                content['duration'] = int(duration)
            except Exception:
                content['duration'] = duration
        if level:
            content['level'] = level
        if objectives:
            content['objectives'] = objectives

        # populate convenience columns for easier querying from admin UI
        lesson = Lesson(
            title=title.strip(),
            course_id=int(course_id),
            content_json=content if content else None,
            description=content.get('description') if isinstance(content, dict) and content.get('description') else (description if description else None),
            duration=(int(content.get('duration')) if isinstance(content, dict) and content.get('duration') and str(content.get('duration')).isdigit() else (int(duration) if duration and str(duration).isdigit() else None)),
            level=(content.get('level') if isinstance(content, dict) and content.get('level') else (level if level else None)),
            objectives=(content.get('objectives') if isinstance(content, dict) and content.get('objectives') else (objectives if objectives else None))
        )
        db.session.add(lesson)
        db.session.commit()
    except Exception:
        current_app.logger.exception('Failed to create lesson')
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "failed to create lesson"}, 500
        flash('Failed to create lesson', 'error')
        return redirect(url_for('admin_bp.lesson_page'))

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return {"success": True, "id": lesson.id}, 201

    # redirect to topic creation for the newly created lesson
    return redirect(url_for('admin_bp.create_topic_page') + f'?lesson_id={lesson.id}')


@admin_bp.route('/update_lesson', methods=['POST'])
def update_lesson_post():
    """Update an existing lesson from admin UI. Accepts JSON or form data.
    Expected fields: id (or lesson_id), title, course_id, description, duration, level, objectives.
    Returns JSON for XHR or redirects back to lesson page.
    """
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))

    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return redirect(url_for('admin_bp.admin_login_get'))

    data = request.get_json(silent=True) or request.form or {}
    lid = data.get('id') or data.get('lesson_id')
    if not lid:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "missing lesson id"}, 400
        flash('Missing lesson id', 'error')
        return redirect(url_for('admin_bp.lesson_page'))

    lesson = Lesson.query.get(lid)
    if not lesson:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "lesson not found"}, 404
        flash('Lesson not found', 'error')
        return redirect(url_for('admin_bp.lesson_page'))

    # update fields
    title = data.get('title') or data.get('lessonTitle')
    course_id = data.get('course_id') or data.get('courseId')
    description = data.get('description') or data.get('lessonDescription')
    duration = data.get('duration') or data.get('lessonDuration')
    level = data.get('level') or data.get('lessonLevel')
    objectives = data.get('objectives') or data.get('lessonObjectives')

    try:
        if title:
            lesson.title = title.strip()
        if course_id:
            lesson.course_id = int(course_id)
        if description is not None:
            lesson.description = description
        if duration is not None and str(duration).isdigit():
            lesson.duration = int(duration)
        if level is not None:
            lesson.level = level
        if objectives is not None:
            lesson.objectives = objectives

        db.session.commit()
    except Exception:
        current_app.logger.exception('Failed to update lesson')
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "failed to update lesson"}, 500
        flash('Failed to update lesson', 'error')
        return redirect(url_for('admin_bp.lesson_page'))

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return {"success": True, "id": lesson.id}
    return redirect(url_for('admin_bp.lesson_page') + f'?lesson_id={lesson.id}&course_id={lesson.course_id}')


@admin_bp.route('/delete_lesson', methods=['POST'])
def delete_lesson_post():
    """Delete a lesson and its topics from admin UI. Accepts JSON or form with id/lesson_id."""
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))

    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return redirect(url_for('admin_bp.admin_login_get'))

    data = request.get_json(silent=True) or request.form or {}
    lid = data.get('id') or data.get('lesson_id')
    if not lid:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "missing lesson id"}, 400
        flash('Missing lesson id', 'error')
        return redirect(url_for('admin_bp.lesson_page'))

    try:
        # delete topics first
        Topic.query.filter_by(lesson_id=lid).delete()
        Lesson.query.filter_by(id=lid).delete()
        db.session.commit()
    except Exception:
        current_app.logger.exception('Failed to delete lesson')
        db.session.rollback()
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "failed to delete lesson"}, 500
        flash('Failed to delete lesson', 'error')
        return redirect(url_for('admin_bp.lesson_page'))

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return {"success": True, "id": int(lid)}
    return redirect(url_for('admin_bp.lesson_page'))


@admin_bp.route('/logout')
def admin_logout():
    session.pop('admin_user_id', None)
    flash('Logged out', 'info')
    # redirect to the site root (home endpoint)
    return redirect(url_for('home'))
