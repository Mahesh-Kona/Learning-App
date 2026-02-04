from flask import Blueprint, render_template, render_template_string, request, redirect, url_for, session, flash, current_app, send_from_directory
from app.extensions import db
from app.models import User
from app.models import Course, Lesson, Topic, Asset, Student
from sqlalchemy import func
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
import uuid
import json
import os
import secrets
import time
import threading
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime
import traceback
from flask import jsonify
from app.utils.category_store import read_categories, write_category, remove_category
from app.utils.emailer import send_email
from app.utils.dynamic_json import (
    generate_courses_json,
    generate_course_lessons_json,
    generate_lesson_topics_json,
    generate_user_progress_json,
    generate_all_jsons
)


admin_bp = Blueprint('admin_bp', __name__, url_prefix='/admin')


@admin_bp.route('/login', methods=['GET'])
def admin_login_get():
    # Render the admin login page
    # Render the main index page which contains the login form. User requested only index.html remain.
    return render_template('index.html')


@admin_bp.route('/forgot-password', methods=['GET'])
def forgot_password_get():
    return render_template('forgot_password.html')


@admin_bp.route('/forgot-password', methods=['POST'])
def forgot_password_post():
    """Send an OTP to admin/teacher email for password reset."""
    email_raw = (request.form.get('email') or '').strip()
    if not email_raw:
        flash('Please enter your email address.', 'error')
        return redirect(url_for('admin_bp.forgot_password_get'))

    email_norm = email_raw.lower()

    # Only allow admin/teacher accounts to reset via this UI flow
    user = None
    try:
        user = User.query.filter(func.lower(User.email) == email_norm).first()
    except Exception:
        # Fallback for DBs that behave differently
        try:
            user = User.query.filter(User.email.ilike(email_norm)).first()
        except Exception:
            user = None

    if not user or user.role not in ('admin', 'teacher'):
        flash('No admin/teacher account found for this email.', 'error')
        return redirect(url_for('admin_bp.forgot_password_get'))

    otp = f"{secrets.randbelow(10000):04d}"
    now = int(time.time())
    expires_at = now + 10 * 60  # 10 minutes

    session['pwreset'] = {
        'type': 'user',
        'user_id': int(user.id),
        'email': email_norm,
        'otp_hash': generate_password_hash(otp),
        'expires_at': expires_at,
        'verified': False,
        'verified_at': None,
        'sent_at': now,
    }

    subject = 'EduSaint Password Reset OTP'
    body = (
        'Hi,\n\n'
        'Use the OTP below to reset your EduSaint password:\n\n'
        f'OTP: {otp}\n\n'
        'This OTP expires in 10 minutes.\n\n'
        'If you did not request this, please ignore this email.\n\n'
        'Regards,\n'
        'EduSaint\n'
    )

    # Don't block the request on SMTP/network. Send in a background thread so the
    # user lands on the OTP page immediately.
    app_obj = current_app._get_current_object()

    def _send_pwreset_email() -> None:
        try:
            with app_obj.app_context():
                sent_ok, err = send_email(to_email=user.email, subject=subject, body=body)
                if not sent_ok:
                    # In dev environments SMTP may not be configured; log OTP so the flow can still be tested.
                    current_app.logger.warning(
                        'Password reset OTP for %s is %s (email send failed: %s)',
                        email_norm,
                        otp,
                        err,
                    )
        except Exception:
            # Never let email issues break the reset flow.
            try:
                with app_obj.app_context():
                    current_app.logger.exception('Failed to send password reset OTP email')
            except Exception:
                pass

    threading.Thread(target=_send_pwreset_email, daemon=True).start()
    flash('OTP is being sent to your email. Please check your inbox (and spam).', 'success')

    return redirect(url_for('admin_bp.otp_get'))


@admin_bp.route('/otp', methods=['GET'])
def otp_get():
    pwreset = session.get('pwreset') or {}
    if not pwreset:
        flash('Please request an OTP first.', 'error')
        return redirect(url_for('admin_bp.forgot_password_get'))
    return render_template('otp.html')


@admin_bp.route('/otp', methods=['POST'])
def otp_post():
    """Verify OTP from the user. If valid, allow password reset."""
    pwreset = session.get('pwreset') or {}
    if not pwreset:
        flash('Please request an OTP first.', 'error')
        return redirect(url_for('admin_bp.forgot_password_get'))

    expires_at = int(pwreset.get('expires_at') or 0)
    now = int(time.time())
    if expires_at <= now:
        session.pop('pwreset', None)
        flash('OTP expired. Please request a new OTP.', 'error')
        return redirect(url_for('admin_bp.forgot_password_get'))

    d1 = (request.form.get('otp1') or '').strip()
    d2 = (request.form.get('otp2') or '').strip()
    d3 = (request.form.get('otp3') or '').strip()
    d4 = (request.form.get('otp4') or '').strip()
    otp = f"{d1}{d2}{d3}{d4}"

    if len(otp) != 4 or not otp.isdigit():
        flash('Please enter the 4-digit OTP.', 'error')
        return redirect(url_for('admin_bp.otp_get'))

    try:
        from werkzeug.security import check_password_hash
        ok = check_password_hash(str(pwreset.get('otp_hash') or ''), otp)
    except Exception:
        ok = False

    if not ok:
        flash('Invalid OTP. Please try again.', 'error')
        return redirect(url_for('admin_bp.otp_get'))

    pwreset['verified'] = True
    pwreset['verified_at'] = now
    session['pwreset'] = pwreset

    flash('OTP verified. You can now reset your password.', 'success')
    return redirect(url_for('admin_bp.reset_password_get'))


@admin_bp.route('/reset-password', methods=['GET'])
def reset_password_get():
    pwreset = session.get('pwreset') or {}
    if not pwreset:
        flash('Please request an OTP first.', 'error')
        return redirect(url_for('admin_bp.forgot_password_get'))
    if not pwreset.get('verified'):
        flash('Please verify OTP before resetting password.', 'error')
        return redirect(url_for('admin_bp.otp_get'))
    return render_template('reset.html')


@admin_bp.route('/reset-password', methods=['POST'])
def reset_password_post():
    """Update password for the verified reset session."""
    pwreset = session.get('pwreset') or {}
    if not pwreset or not pwreset.get('verified'):
        flash('Please verify OTP before resetting password.', 'error')
        return redirect(url_for('admin_bp.forgot_password_get'))

    expires_at = int(pwreset.get('expires_at') or 0)
    now = int(time.time())
    if expires_at <= now:
        session.pop('pwreset', None)
        flash('Reset session expired. Please request a new OTP.', 'error')
        return redirect(url_for('admin_bp.forgot_password_get'))

    new_password = (request.form.get('new_password') or '').strip()
    confirm_password = (request.form.get('confirm_password') or '').strip()
    if not new_password or not confirm_password:
        flash('Please enter and confirm your new password.', 'error')
        return redirect(url_for('admin_bp.reset_password_get'))
    if new_password != confirm_password:
        flash('Passwords do not match.', 'error')
        return redirect(url_for('admin_bp.reset_password_get'))
    if len(new_password) < 6:
        flash('Password must be at least 6 characters.', 'error')
        return redirect(url_for('admin_bp.reset_password_get'))

    if pwreset.get('type') == 'user':
        user_id = pwreset.get('user_id')
        user = User.query.get(int(user_id)) if user_id is not None else None
        if not user:
            session.pop('pwreset', None)
            flash('Account not found. Please try again.', 'error')
            return redirect(url_for('admin_bp.forgot_password_get'))
        if user.role not in ('admin', 'teacher'):
            session.pop('pwreset', None)
            flash('This account is not eligible for this reset flow.', 'error')
            return redirect(url_for('admin_bp.forgot_password_get'))
        user.set_password(new_password)
        db.session.commit()
    else:
        session.pop('pwreset', None)
        flash('Unsupported reset target.', 'error')
        return redirect(url_for('admin_bp.forgot_password_get'))

    session.pop('pwreset', None)
    flash('Password updated. Please login with your new password.', 'success')
    return redirect(url_for('admin_bp.admin_login_get'))


@admin_bp.route('/login', methods=['POST'])
def admin_login_post():
    # Simple session-based admin login for the admin UI
    email = request.form.get('email') or request.form.get('username')
    password = request.form.get('password')
    if not email or not password:
        flash('Missing credentials', 'error')
        return redirect(url_for('admin_bp.admin_login_get'))

    # The admin dashboard is only accessible when selecting the Admin role.
    selected_role = request.form.get('role') or (request.get_json(silent=True) or {}).get('role')
    if selected_role != 'admin':
        msg = 'Please select Admin to access the admin dashboard'
        # detect XHR callers so we can return JSON for AJAX logins
        is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if is_xhr:
            return {"success": False, "error": msg}, 401
        flash(msg, 'error')
        return redirect(url_for('admin_bp.admin_login_get'))

    # detect XHR callers so we can return JSON for AJAX logins
    is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    email = str(email).strip().lower()

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
        session['admin_role'] = 'admin'
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
        user = User.query.filter(func.lower(User.email) == email).first()
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
        session['admin_role'] = 'admin'
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

    # Fallback: allow Staff accounts to access the admin dashboard when they selected Admin.
    # Staff credentials live in the `staff` table (not the `users` table), but the admin UI
    # expects a `users` row with role=admin for downstream checks.
    try:
        from app.models import Staff

        staff = Staff.query.filter(func.lower(Staff.email) == email).first()
        if staff and staff.status == 'active' and staff.check_password(password):
            # Link or create an admin User record for this staff account.
            admin_user = User.query.filter(func.lower(User.email) == email).first()
            if admin_user is None:
                admin_user = User(email=email, role='admin')
                admin_user.set_password(password)
                db.session.add(admin_user)
                db.session.flush()
            elif admin_user.role != 'admin':
                # Avoid implicitly escalating an existing non-admin user.
                admin_user = None

            if admin_user is not None:
                # Keep a link for future joins/debugging.
                try:
                    staff.user_id = admin_user.id
                    staff.last_login_at = datetime.utcnow()
                except Exception:
                    pass

                # Honor remember flag here as well.
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
                session['admin_user_id'] = admin_user.id
                session['admin_role'] = 'admin'
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()

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
                flash('Welcome!', 'success')
                return redirect(url_for('admin_bp.admin_dashboard'))
    except Exception:
        current_app.logger.exception('Staff login fallback failed')

    # otherwise invalid
    msg = 'Invalid admin credentials'
    if is_xhr:
        return {"success": False, "error": msg}, 401
    flash(msg, 'error')
    return redirect(url_for('admin_bp.admin_login_get'))


@admin_bp.route('/api/get-jwt-token', methods=['GET'])
def get_jwt_token():
    """Generate JWT token for session-authenticated admin users."""
    from flask_jwt_extended import create_access_token
    
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    
    # Get user email from database or use dev admin
    email = 'admin@example.com'
    role = 'admin'
    
    if uid != 'dev_admin':
        try:
            user = User.query.get(uid)
            if user:
                email = user.email
                role = user.role
        except Exception:
            pass
    
    # Create JWT token
    # The identity must be a simple type (string). We'll use user_id as identity
    # and pass additional claims via additional_claims parameter
    user_id_str = str(uid)
    additional_claims = {
        'email': email,
        'role': role
    }
    
    access_token = create_access_token(identity=user_id_str, additional_claims=additional_claims)
    return jsonify({'success': True, 'access_token': access_token}), 200
    
@admin_bp.route('/whoami')
def whoami():
    user_id = session.get('admin_user_id')
    role = session.get('admin_role')
    if not user_id:
        return jsonify({'user': None, 'role': None}), 200
    if user_id == 'dev_admin':
        username = 'dev_admin'
    else:
        from app.models import User
        try:
            user = User.query.get(int(user_id))
            username = user.username if user else str(user_id)
        except Exception:
            username = str(user_id)
    return jsonify({'user': username, 'role': role}), 200
    return jsonify({
        'success': True,
        'access_token': access_token
    }), 200


@admin_bp.route('/dashboard')
def admin_dashboard():
    uid = session.get('admin_user_id')
    if not uid:
        return redirect(url_for('admin_bp.admin_login_get'))

    # Support dev admin sentinel value â€” create a lightweight user-like object for templates
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
    # Fetch recently added students ordered by join date (students.date)
    recent_students = []
    recent_courses = []
    recent_staff = []
    scheduled_notifications_count = 0
    total_students_count = 0
    total_staff_count = 0
    try:
        recent_students = Student.query.order_by(Student.date.desc()).limit(10).all()
    except Exception:
        recent_students = []

    # Fetch recently created courses
    try:
        from app.models import Course
        recent_courses = Course.query.order_by(Course.created_at.desc()).limit(10).all()
    except Exception:
        recent_courses = []

    # Fetch recently added staff
    try:
        from app.models import Staff as StaffModel
        recent_staff = StaffModel.query.order_by(StaffModel.created_at.desc()).limit(10).all()
    except Exception:
        recent_staff = []

    # Count total students
    try:
        total_students_count = Student.query.count()
    except Exception:
        total_students_count = 0

    # Count total staff
    try:
        from app.models import Staff
        total_staff_count = Staff.query.count()
    except Exception:
        total_staff_count = 0

    # Count scheduled notifications
    try:
        from app.models import Notification
        scheduled_notifications_count = Notification.query.filter(Notification.status == 'scheduled').count()
    except Exception:
        scheduled_notifications_count = 0

    # Build a unified recent_activity list (max 5 items) with human-friendly time labels
    recent_activity = []

    def _humanize_ago(ts, now):
        if not ts:
            return None
        try:
            delta = now - ts
        except Exception:
            return None

        seconds = int(delta.total_seconds())
        if seconds < 0:
            return 'just now'
        if seconds < 60:
            return 'just now'

        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} min{'s' if minutes != 1 else ''} ago"

        hours = seconds // 3600
        if hours < 24:
            return f"{hours} hour{'s' if hours != 1 else ''} ago"

        days = delta.days
        if days < 7:
            return f"{days} day{'s' if days != 1 else ''} ago"

        # Older than a week: fall back to a calendar date
        try:
            return ts.strftime('%d %b %Y')
        except Exception:
            return None

    now = datetime.utcnow()

    # Student activities
    for s in recent_students or []:
        ts = getattr(s, 'date', None) or getattr(s, 'created_at', None)
        if not ts:
            continue
        label = _humanize_ago(ts, now)
        if not label:
            continue
        recent_activity.append({
            'kind': 'student',
            'timestamp': ts,
            'ago': label,
            'name': getattr(s, 'name', None) or 'Unknown student',
            'class_name': getattr(s, 'class_', None) or getattr(s, 'syllabus', None) or 'N/A',
        })

    # Course activities
    for c in recent_courses or []:
        ts = getattr(c, 'created_at', None)
        if not ts:
            continue
        label = _humanize_ago(ts, now)
        if not label:
            continue
        recent_activity.append({
            'kind': 'course',
            'timestamp': ts,
            'ago': label,
            'title': getattr(c, 'title', None) or 'Untitled course',
            'class_name': getattr(c, 'class_name', None),
        })

    # Staff activities
    for st in recent_staff or []:
        ts = getattr(st, 'created_at', None)
        if not ts and getattr(st, 'join_date', None):
            try:
                ts = datetime.combine(st.join_date, datetime.min.time())
            except Exception:
                ts = None
        if not ts:
            continue
        label = _humanize_ago(ts, now)
        if not label:
            continue
        recent_activity.append({
            'kind': 'staff',
            'timestamp': ts,
            'ago': label,
            'name': getattr(st, 'name', None) or 'Unknown staff',
            'role': getattr(st, 'role', None),
        })

    # Sort by most recent and keep only top 5 items
    try:
        recent_activity.sort(key=lambda a: a.get('timestamp') or datetime.min, reverse=True)
    except Exception:
        pass
    recent_activity = recent_activity[:5]

    try:
        return render_template(
            'dashboard.html',
            user=user,
            active='dashboard',
            recent_students=recent_students,
            recent_courses=recent_courses,
            recent_staff=recent_staff,
            recent_activity=recent_activity,
            scheduled_notifications_count=scheduled_notifications_count,
            total_students_count=total_students_count,
            total_staff_count=total_staff_count,
        )
    except Exception:
        project_root = os.path.abspath(os.path.join(current_app.root_path, '..'))
        candidate = os.path.join(project_root, 'templates', 'dashboard.html')
        if os.path.exists(candidate):
            try:
                with open(candidate, 'r', encoding='utf8') as fh:
                    content = fh.read()
                return render_template_string(
                    content,
                    user=user,
                    active='dashboard',
                    recent_students=recent_students,
                    recent_activity=recent_activity,
                    scheduled_notifications_count=scheduled_notifications_count,
                    total_students_count=total_students_count,
                    total_staff_count=total_staff_count,
                )
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


@admin_bp.route('/students', methods=['GET'])
def students_page():
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

    # Render the student management template
    return render_template('student.html', user=user, active='students')


@admin_bp.route('/staff', methods=['GET'])
def staff_management_page():
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

    return render_template('staff_management.html', user=user, active='staff')


def _staff_status_to_db(value: str | None) -> str:
    v = (value or '').strip().lower()
    if v in {'active', 'inactive'}:
        return v
    if v == 'inactive':
        return 'inactive'
    # UI uses "Active"/"Inactive"; default to active
    return 'active'


def _staff_status_to_ui(value: str | None) -> str:
    v = (value or 'active').strip().lower()
    return 'Inactive' if v == 'inactive' else 'Active'


def _staff_to_dict(staff):
    avatar_url = None
    try:
        img_path = (staff.avatar or '').strip()
        if img_path:
            img_path = img_path.lstrip('/')
            first_segment = img_path.split('/')[0]
            if first_segment.lower() != 'avatars':
                fname = os.path.basename(img_path)
                img_path = f"avatars/{fname}"
            avatar_url = url_for('uploaded_file', filename=img_path)
    except Exception:
        avatar_url = None
    return {
        'id': staff.id,
        'name': staff.name,
        'gender': staff.gender,
        'role': staff.role,
        'department': staff.department or '',
        'email': staff.email,
        'phone': staff.phone,
        'city': staff.city or '',
        'joinDate': staff.join_date.isoformat() if getattr(staff, 'join_date', None) else None,
        'status': _staff_status_to_ui(getattr(staff, 'status', None)),
        # front-end expects a usable URL
        'avatar': avatar_url,
        'permissions': staff.permissions or [],
        'sendEmail': bool(getattr(staff, 'send_email', True)),
        'sendSms': bool(getattr(staff, 'send_sms', False)),
        'lastLoginAt': staff.last_login_at.isoformat() if getattr(staff, 'last_login_at', None) else None,
        'createdAt': staff.created_at.isoformat() if getattr(staff, 'created_at', None) else None,
        'updatedAt': staff.updated_at.isoformat() if getattr(staff, 'updated_at', None) else None,
    }


@admin_bp.route('/staff/api/<int:staff_id>/avatar', methods=['POST'])
def staff_api_upload_avatar(staff_id: int):
    """Upload avatar image for a staff member.

    Expects multipart/form-data with 'avatar' file field.
    Stores file under uploads/avatars and persists staff.avatar as '/avatars/<filename>'.
    """
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    if 'avatar' not in request.files:
        return jsonify({'success': False, 'error': 'No avatar file provided'}), 400

    file = request.files['avatar']
    if not file or file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    allowed_extensions = {'jpg', 'jpeg', 'png'}
    filename = secure_filename(file.filename)
    file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if file_ext not in allowed_extensions:
        return jsonify({'success': False, 'error': f"Invalid file type. Allowed: {', '.join(sorted(allowed_extensions))}"}), 400

    # Match UI guidance (100KB)
    try:
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > 100 * 1024:
            return jsonify({'success': False, 'error': 'File too large. Maximum size: 100KB'}), 400
    except Exception:
        # If size check fails, continue (best-effort)
        pass

    from app.extensions import db
    try:
        from app.models import Staff
        staff = Staff.query.get(staff_id)
        if not staff:
            return jsonify({'success': False, 'error': 'Not found'}), 404

        upload_base = current_app.config.get('UPLOAD_PATH', 'uploads')
        if not Path(upload_base).is_absolute():
            project_root = Path(current_app.root_path).parent
            upload_base = project_root / upload_base

        avatars_dir = Path(upload_base) / 'avatars'
        avatars_dir.mkdir(parents=True, exist_ok=True)

        new_filename = f"staff_{staff.id}_avatar.{file_ext}"
        file_path = avatars_dir / new_filename

        # Delete old avatar file if present
        try:
            if staff.avatar:
                old_rel = staff.avatar.lstrip('/')
                # normalize to avatars/<fname>
                if not old_rel.lower().startswith('avatars/'):
                    old_rel = f"avatars/{os.path.basename(old_rel)}"
                old_file_path = Path(upload_base) / old_rel
                if old_file_path.exists() and old_file_path != file_path:
                    old_file_path.unlink()
        except Exception:
            current_app.logger.warning('Failed to delete old staff avatar', exc_info=True)

        file.save(str(file_path))

        staff.avatar = f"/avatars/{new_filename}"
        db.session.commit()

        return jsonify({'success': True, 'staff': _staff_to_dict(staff)}), 200
    except Exception as e:
        current_app.logger.exception('Failed to upload staff avatar')
        try:
            db.session.rollback()
        except Exception:
            pass
        # Include detail to speed up debugging in dev
        return jsonify({'success': False, 'error': 'Upload failed', 'detail': str(e)}), 500


@admin_bp.route('/staff/api', methods=['GET'])
def staff_api_list():
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    try:
        from app.models import Staff
        rows = Staff.query.order_by(Staff.created_at.desc()).all()
        return jsonify({'success': True, 'staff': [_staff_to_dict(s) for s in rows]}), 200
    except Exception:
        current_app.logger.exception('Failed to list staff')
        return jsonify({'success': False, 'error': 'Failed to list staff'}), 500


@admin_bp.route('/staff/api', methods=['POST'])
def staff_api_create():
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    from app.extensions import db
    try:
        from app.models import Staff
        from datetime import date

        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        gender = (data.get('gender') or '').strip().lower()
        email = (data.get('email') or '').strip().lower()
        phone = (data.get('phone') or '').strip()
        role = (data.get('role') or '').strip()
        department = (data.get('department') or '').strip() or None
        city = (data.get('city') or '').strip() or None
        status = _staff_status_to_db(data.get('status'))
        permissions = data.get('permissions') or []
        send_email = bool(data.get('sendEmail', True))
        send_sms = bool(data.get('sendSms', False))
        join_date = None
        join_date_str = (data.get('joinDate') or '').strip()
        if join_date_str:
            try:
                join_date = date.fromisoformat(join_date_str)
            except Exception:
                join_date = None
        if join_date is None:
            join_date = date.today()

        password = data.get('password')

        if not name:
            return jsonify({'success': False, 'error': 'Name is required'}), 400
        if gender not in {'male', 'female', 'other'}:
            return jsonify({'success': False, 'error': 'Gender is required'}), 400
        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        if not phone:
            return jsonify({'success': False, 'error': 'Phone is required'}), 400
        if not role:
            return jsonify({'success': False, 'error': 'Role is required'}), 400
        if not isinstance(permissions, list) or len(permissions) == 0:
            return jsonify({'success': False, 'error': 'At least one permission is required'}), 400

        # Enforce global email uniqueness across Staff, Student, and User tables.
        from app.models import Student as StudentModel, User as UserModel
        existing_staff = Staff.query.filter(func.lower(Staff.email) == email).first()
        existing_student = StudentModel.query.filter(func.lower(StudentModel.email) == email).first()
        existing_user = UserModel.query.filter(func.lower(UserModel.email) == email).first()
        if existing_staff or existing_student or existing_user:
            return jsonify({'success': False, 'error': 'email already exists'}), 400

        notifications = {
            'email': {'requested': bool(send_email), 'sent': False},
            'sms': {'requested': bool(send_sms), 'sent': False},
        }

        staff = Staff(
            name=name,
            gender=gender,
            email=email,
            phone=phone,
            city=city,
            department=department,
            role=role,
            status=status,
            permissions=permissions,
            join_date=join_date,
            send_email=send_email,
            send_sms=send_sms,
        )

        if password:
            staff.set_password(password)

        db.session.add(staff)
        db.session.commit()

        # Send credentials email if requested
        if send_email and password and email:
            try:
                from app.utils.emailer import send_staff_credentials_email

                login_url = url_for('admin_bp.admin_login_get', _external=True)
                sent, err = send_staff_credentials_email(
                    to_email=email,
                    staff_name=name,
                    password=str(password),
                    login_url=login_url,
                )
                notifications['email']['sent'] = bool(sent)
                if err:
                    notifications['email']['error'] = err
            except Exception as e:
                current_app.logger.exception('Failed to send staff credentials email')
                notifications['email']['sent'] = False
                notifications['email']['error'] = str(e)

        return jsonify({'success': True, 'staff': _staff_to_dict(staff), 'notifications': notifications}), 201
    except Exception:
        current_app.logger.exception('Failed to create staff')
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'success': False, 'error': 'Failed to create staff'}), 500


@admin_bp.route('/staff/api/<int:staff_id>', methods=['PUT', 'POST'])
def staff_api_update(staff_id: int):
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    from app.extensions import db
    try:
        from app.models import Staff
        from datetime import date

        staff = Staff.query.get(staff_id)
        if not staff:
            return jsonify({'success': False, 'error': 'Not found'}), 404

        data = request.get_json(silent=True) or {}

        if 'name' in data:
            staff.name = (data.get('name') or '').strip() or staff.name
        if 'gender' in data:
            g = (data.get('gender') or '').strip().lower()
            if g in {'male', 'female', 'other'}:
                staff.gender = g
        if 'email' in data:
            e = (data.get('email') or '').strip().lower()
            if e and e != (staff.email or '').strip().lower():
                # Enforce global email uniqueness when changing email
                from app.models import Student as StudentModel, User as UserModel
                existing_staff = Staff.query.filter(func.lower(Staff.email) == e, Staff.id != staff.id).first()
                existing_student = StudentModel.query.filter(func.lower(StudentModel.email) == e).first()
                existing_user = UserModel.query.filter(func.lower(UserModel.email) == e).first()
                if existing_staff or existing_student or existing_user:
                    return jsonify({'success': False, 'error': 'email already exists'}), 400
                staff.email = e
        if 'phone' in data:
            p = (data.get('phone') or '').strip()
            if p:
                staff.phone = p
        if 'city' in data:
            staff.city = (data.get('city') or '').strip() or None
        if 'department' in data:
            staff.department = (data.get('department') or '').strip() or None
        if 'role' in data:
            r = (data.get('role') or '').strip()
            if r:
                staff.role = r
        if 'status' in data:
            staff.status = _staff_status_to_db(data.get('status'))
        if 'permissions' in data:
            perms = data.get('permissions') or []
            if isinstance(perms, list) and len(perms) > 0:
                staff.permissions = perms
        if 'sendEmail' in data:
            staff.send_email = bool(data.get('sendEmail'))
        if 'sendSms' in data:
            staff.send_sms = bool(data.get('sendSms'))
        if 'joinDate' in data:
            jd = (data.get('joinDate') or '').strip()
            if jd:
                try:
                    staff.join_date = date.fromisoformat(jd)
                except Exception:
                    pass
        if 'password' in data and data.get('password'):
            staff.set_password(data.get('password'))

        db.session.commit()
        return jsonify({'success': True, 'staff': _staff_to_dict(staff)}), 200
    except Exception:
        current_app.logger.exception('Failed to update staff')
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'success': False, 'error': 'Failed to update staff'}), 500


@admin_bp.route('/staff/api/<int:staff_id>', methods=['DELETE'])
def staff_api_delete(staff_id: int):
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    from app.extensions import db
    try:
        from app.models import Staff
        staff = Staff.query.get(staff_id)
        if not staff:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        db.session.delete(staff)
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception:
        current_app.logger.exception('Failed to delete staff')
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'success': False, 'error': 'Failed to delete staff'}), 500


@admin_bp.route('/staff/api/<int:staff_id>/delete', methods=['POST'])
def staff_api_delete_fallback(staff_id: int):
    """Fallback delete endpoint for environments where DELETE is blocked upstream."""
    return staff_api_delete(staff_id)


@admin_bp.route('/analytics', methods=['GET'])
def analytics_page():
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

    return render_template('analytics.html', user=user, active='analytics')


@admin_bp.route('/students/<int:student_id>', methods=['GET'])
def view_student(student_id: int):
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

    student = None
    try:
        student = Student.query.get(student_id)
    except Exception:
        student = None

    if not student:
        flash('Student not found', 'error')
        return redirect(url_for('admin_bp.admin_dashboard'))

    # Build avatar URL for the template, mapping stored path to /uploads route
    avatar_url = None
    try:
        img_path = (student.image or '').strip()
        if img_path:
            # remove any leading slash
            img_path = img_path.lstrip('/')
            # ensure path points to avatars folder under uploads
            # if not already under 'avatars/', take basename and prepend
            first_segment = img_path.split('/')[0]
            if first_segment.lower() != 'avatars':
                fname = os.path.basename(img_path)
                img_path = f"avatars/{fname}"
            avatar_url = url_for('uploaded_file', filename=img_path)
    except Exception:
        avatar_url = None

    return render_template('student_detail.html', user=user, active='students', student=student, avatar_url=avatar_url)


# Card Type Editors
@admin_bp.route('/quiz-editor', methods=['GET'])
def quiz_editor():
    return render_template('quiz.html')


@admin_bp.route('/concept-editor', methods=['GET'])
def concept_editor():
    return render_template('concept.html')


@admin_bp.route('/video-editor', methods=['GET'])
def video_editor():
    # Require admin session similar to other admin pages
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

    # Pass through optional context for saving cards
    topic_id = request.args.get('topic_id')
    lesson_id = request.args.get('lesson_id')
    display_order = request.args.get('display_order', 0)

    return render_template('video.html', user=user, topic_id=topic_id, lesson_id=lesson_id, display_order=display_order)


@admin_bp.route('/interactive-editor', methods=['GET'])
def interactive_editor():
    return render_template('interactive.html')


@admin_bp.route('/notifications', methods=['GET'])
def notifications_page():
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

    return render_template('notifications.html', user=user, active='notifications')


@admin_bp.route('/notifications/api', methods=['GET'])
def notifications_api_list():
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    try:
        from app.models import Notification
        rows = Notification.query.order_by(Notification.created_at.desc()).all()
        out = []
        for n in rows:
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
        return jsonify(out), 200
    except Exception:
        current_app.logger.exception('Failed to list notifications')
        return jsonify({'success': False, 'error': 'Failed to list'}), 500


@admin_bp.route('/notifications/api', methods=['POST'])
def notifications_api_create():
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    try:
        from app.models import Notification
        from app.extensions import db
        data = request.get_json(silent=True) or {}
        title = (data.get('title') or '').strip()
        message = (data.get('message') or '').strip()
        category = (data.get('category') or 'info').strip()
        target = (data.get('target') or '').strip()
        date = data.get('date')
        time = data.get('time')
        if not title or not message:
            return jsonify({'success': False, 'error': 'Title and message required'}), 400
        scheduled_at = None
        status = 'Sent'
        if date and time:
            try:
                from datetime import datetime
                scheduled_at = datetime.fromisoformat(f"{date} {time}")
                status = 'Scheduled'
                # Validate: scheduled time must be in the future
                now = datetime.now()
                if scheduled_at <= now:
                    return jsonify({'success': False, 'error': 'Schedule must be in the future'}), 400
            except Exception:
                scheduled_at = None
        n = Notification(title=title, message=message, category=category, target=target or 'all', status=status, scheduled_at=scheduled_at)
        db.session.add(n)
        db.session.commit()
        return jsonify({'success': True, 'id': n.id}), 201
    except Exception:
        current_app.logger.exception('Failed to create notification')
        try:
            from app.extensions import db
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'success': False, 'error': 'Failed to create'}), 500


@admin_bp.route('/notifications/api/<int:notification_id>', methods=['PUT'])
def notifications_api_update(notification_id):
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    try:
        from app.models import Notification
        from app.extensions import db
        n = Notification.query.get(notification_id)
        if not n:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        data = request.get_json(silent=True) or {}
        n.title = (data.get('title') or n.title)
        n.message = (data.get('message') or n.message)
        n.category = (data.get('category') or n.category)
        n.target = (data.get('target') or n.target)
        # Allow updating schedule with validation for future times only
        date = data.get('date')
        time = data.get('time')
        if date and time:
            try:
                from datetime import datetime
                new_sched = datetime.fromisoformat(f"{date} {time}")
                now = datetime.now()
                if new_sched <= now:
                    return jsonify({'success': False, 'error': 'Schedule must be in the future'}), 400
                n.scheduled_at = new_sched
                n.status = 'Scheduled'
            except Exception:
                return jsonify({'success': False, 'error': 'Invalid schedule date/time'}), 400
        elif date is not None or time is not None:
            # If one of date/time was intentionally cleared, treat as immediate send
            n.scheduled_at = None
            n.status = 'Sent'
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception:
        current_app.logger.exception('Failed to update notification')
        try:
            from app.extensions import db
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'success': False, 'error': 'Failed to update'}), 500


@admin_bp.route('/notifications/api/<int:notification_id>', methods=['DELETE'])
def notifications_api_delete(notification_id):
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    try:
        from app.models import Notification
        from app.extensions import db
        n = Notification.query.get(notification_id)
        if not n:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        db.session.delete(n)
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception:
        current_app.logger.exception('Failed to delete notification')
        try:
            from app.extensions import db
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'success': False, 'error': 'Failed to delete'}), 500


@admin_bp.route('/notifications/api/<int:notification_id>/delete', methods=['POST'])
def notifications_api_delete_fallback(notification_id):
    """Fallback delete endpoint for environments where DELETE is blocked upstream.

    Performs the same deletion as notifications_api_delete but via POST.
    """
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    try:
        from app.models import Notification
        from app.extensions import db
        n = Notification.query.get(notification_id)
        if not n:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        db.session.delete(n)
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception:
        current_app.logger.exception('Failed to delete notification (POST fallback)')
        try:
            from app.extensions import db
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'success': False, 'error': 'Failed to delete'}), 500


@admin_bp.route('/notifications/api/<int:notification_id>', methods=['GET'])
def notifications_api_get(notification_id):
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    try:
        from app.models import Notification
        n = Notification.query.get(notification_id)
        if not n:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        return jsonify({
            'success': True,
            'notification': {
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'category': n.category,
                'target': n.target,
                'status': n.status,
                'scheduled_at': n.scheduled_at.isoformat() if getattr(n, 'scheduled_at', None) else None,
                'created_at': n.created_at.isoformat() if getattr(n, 'created_at', None) else None
            }
        }), 200
    except Exception:
        current_app.logger.exception('Failed to get notification')
        return jsonify({'success': False, 'error': 'Failed to get'}), 500


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
                # expose duration_weeks to the template as duration
                'duration': c.duration_weeks,
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

    # Render the category management template. The template will fetch courses via AJAX.
    return render_template('category-management.html', user=user, active='categories')



@admin_bp.route('/get_courses', methods=['GET'])
def get_courses():
    """Return a JSON list of courses. Supports optional query params: q, type, difficulty."""
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'error': 'unauthorized'}), 401

    # Basic admin check
    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return jsonify({'error': 'unauthorized'}), 401

    q = (request.args.get('q') or '').strip()
    type_filter = (request.args.get('type') or '').strip()
    difficulty_filter = (request.args.get('difficulty') or '').strip()

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
                'name': c.title or '',
                'icon': 'ðŸ“š',
                'description': c.description or '',
                'subjectType': getattr(c, 'category', '') or '',
                'difficulty': getattr(c, 'difficulty', '') or '',
                'parentId': None,
                'order': 1,
                'coursesCount': lessons_count
            })
    except Exception:
        courses = []

    # Apply simple filters in Python for stability (works even if model lacks fields)
    def matches(item):
        if q:
            qlow = q.lower()
            if qlow not in (item.get('name') or '').lower() and qlow not in (item.get('description') or '').lower():
                return False
        if type_filter:
            if type_filter.lower() != (item.get('subjectType') or '').lower():
                return False
        if difficulty_filter:
            if difficulty_filter.lower() != (item.get('difficulty') or '').lower():
                return False
        return True

    filtered = [c for c in courses if matches(c)]
    return jsonify({'courses': filtered}), 200


@admin_bp.route('/get_categories', methods=['GET'])
def get_categories():
    """Return aggregated categories from Course.category column with counts."""
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'error': 'unauthorized'}), 401

    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return jsonify({'error': 'unauthorized'}), 401

    try:
        # group by category and count courses per category
        rows = db.session.query(Course.category, func.count(Course.id)).group_by(Course.category).all()
        categories = []
        for cat, cnt in rows:
            if not cat:
                continue
            categories.append({'name': cat, 'count': int(cnt)})
        # include persisted categories from the category store (zero-count allowed)
        try:
            stored = read_categories(current_app.root_path)
            # stored is list of {name:..., ...}
            for s in stored:
                if not s or not s.get('name'):
                    continue
                name = s.get('name')
                # if already present, skip
                if any(c['name'].lower() == name.lower() for c in categories):
                    continue
                categories.append({'name': name, 'count': 0})
        except Exception:
            current_app.logger.exception('Failed to read stored categories')

        return jsonify({'categories': categories}), 200
    except Exception:
        current_app.logger.exception('Failed to fetch categories')
        return jsonify({'categories': []}), 200



@admin_bp.route('/create_category', methods=['POST'])
def create_category():
    """Persist a new category to the lightweight category store (JSON file).
    This avoids requiring a DB migration for a simple admin-managed list.
    """
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return jsonify({'success': False, 'error': 'unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    name = data.get('name')
    if not name:
        return jsonify({'success': False, 'error': 'missing name'}), 400

    # write to store
    ok = write_category({
        'name': name,
        'icon': data.get('icon'),
        'description': data.get('description'),
        'subjectType': data.get('subjectType'),
        'difficulty': data.get('difficulty')
    }, current_app.root_path)

    if not ok:
        return jsonify({'success': False, 'error': 'failed to persist category'}), 500

    return jsonify({'success': True, 'name': name}), 201



@admin_bp.route('/delete_category', methods=['POST'])
def delete_category():
    """Remove a category from the lightweight category store (JSON file).
    This does not affect Course.category values (clear_category handles that).
    """
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return jsonify({'success': False, 'error': 'unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    name = data.get('name')
    if not name:
        return jsonify({'success': False, 'error': 'missing name'}), 400

    try:
        ok = remove_category(name, current_app.root_path)
        if not ok:
            return jsonify({'success': False, 'error': 'not found or failed to remove'}), 404
        return jsonify({'success': True, 'name': name}), 200
    except Exception:
        current_app.logger.exception('Failed to delete stored category %s', name)
        return jsonify({'success': False, 'error': 'failed to delete category'}), 500


@admin_bp.route('/rename_category', methods=['POST'])
def rename_category():
    """Rename category on all courses from old_name -> new_name."""
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return jsonify({'success': False, 'error': 'unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    old = data.get('old') or data.get('old_name')
    new = data.get('new') or data.get('new_name')
    if not old or new is None:
        return jsonify({'success': False, 'error': 'missing parameters'}), 400

    try:
        # update all Course rows where category equals old
        updated = Course.query.filter(Course.category == old).update({ 'category': (new or None) })
        db.session.commit()
        return jsonify({'success': True, 'updated': int(updated)}), 200
    except Exception:
        current_app.logger.exception('Failed to rename category %s -> %s', old, new)
        try:
            db.session.rollback()
        except Exception:
            current_app.logger.exception('rollback failed after rename_category failure')
        return jsonify({'success': False, 'error': 'failed to rename category'}), 500


@admin_bp.route('/clear_category', methods=['POST'])
def clear_category():
    """Clear category on all courses with given name (set to NULL)."""
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return jsonify({'success': False, 'error': 'unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    name = data.get('name')
    if not name:
        return jsonify({'success': False, 'error': 'missing name'}), 400

    try:
        updated = Course.query.filter(Course.category == name).update({ 'category': None })
        db.session.commit()
        return jsonify({'success': True, 'updated': int(updated)}), 200
    except Exception:
        current_app.logger.exception('Failed to clear category %s', name)
        try:
            db.session.rollback()
        except Exception:
            current_app.logger.exception('rollback failed after clear_category failure')
        return jsonify({'success': False, 'error': 'failed to clear category'}), 500


@admin_bp.route('/get_lessons', methods=['GET'])
def get_lessons():
    """Return lessons for a given course_id. Query param: course_id"""
    uid = session.get('admin_user_id')
    if not uid:
        return jsonify({'error': 'unauthorized'}), 401

    if uid == 'dev_admin':
        user = None
    else:
        user = User.query.get(uid)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return jsonify({'error': 'unauthorized'}), 401

    try:
        cid = int(request.args.get('course_id') or 0)
    except Exception:
        cid = 0

    if not cid:
        return jsonify({'lessons': []}), 200

    try:
        lessons_q = Lesson.query.filter_by(course_id=cid).order_by(Lesson.title).all()
        lessons = [{'id': l.id, 'title': l.title or ''} for l in lessons_q]
    except Exception:
        lessons = []

    return jsonify({'lessons': lessons}), 200


@admin_bp.route('/all_topics', methods=['GET'])
def all_topics_page():
    # Legacy route no longer used now that Course Content Management handles topics.
    # Keep a lightweight redirect for any old links.
    return redirect(url_for('admin_bp.admin_dashboard'))


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
                    # store estimated time and mirror it into duration for topics
                    try:
                        parsed_est = int(est)
                    except Exception:
                        parsed_est = est
                    data_json['estimated_time'] = parsed_est
                    # only set duration if not already explicitly provided
                    if 'duration' not in data_json:
                        data_json['duration'] = parsed_est
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
            # also grab estimated_time and difficulty when sent via JSON (Course Content page)
            estimated_time = data.get('estimated_time') or data.get('estimatedTime')
            difficulty = data.get('difficulty') or data.get('topicDifficulty') or data.get('topic_difficulty')

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
            # try to coerce to int when possible, and mirror into duration
            try:
                parsed_est = int(estimated_time)
            except Exception:
                parsed_est = estimated_time
            payload['estimated_time'] = parsed_est
            if 'duration' not in payload:
                payload['duration'] = parsed_est
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

    # If no explicit topic order was provided, compute next order within this lesson
    try:
        if lesson_id and (not isinstance(data_json, dict) or data_json.get('order') is None):
            if not isinstance(data_json, dict):
                data_json = data_json or {}
                if not isinstance(data_json, dict):
                    data_json = {}
            existing_topics = Topic.query.filter_by(lesson_id=int(lesson_id)).all()
            max_order = 0
            for t in existing_topics:
                d = t.data_json if isinstance(t.data_json, dict) else {}
                if isinstance(d, dict) and d.get('order') is not None:
                    try:
                        val = int(d.get('order'))
                    except Exception:
                        continue
                    if val > max_order:
                        max_order = val
            if max_order == 0 and existing_topics:
                max_order = len(existing_topics)
            data_json['order'] = max_order + 1
    except Exception:
        # best-effort; if it fails, topic will still be created
        pass

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
    is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
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

        # Rebuild data_json so that editable attributes from the admin UI
        # (description, estimated_time/duration, difficulty, order, icon)
        # are kept in sync, while preserving any unknown keys (e.g. cards).
        meta = {}

        desc = data.get('description')
        if desc is not None:
            meta['description'] = desc

        est = data.get('estimated_time')
        if est is not None and est != '':
            # keep both estimated_time and duration coherent
            try:
                parsed_est = int(est)
            except Exception:
                parsed_est = est
            meta['estimated_time'] = parsed_est
            meta['duration'] = parsed_est

        diff = data.get('difficulty')
        if diff is not None:
            meta['difficulty'] = diff

        ttype = data.get('type')
        if ttype is not None:
            meta['type'] = ttype

        order_val = data.get('order')
        if order_val is not None and order_val != '':
            try:
                parsed_order = int(order_val)
            except Exception:
                parsed_order = order_val
            meta['order'] = parsed_order

        icon_val = data.get('icon')
        if icon_val is not None:
            meta['icon'] = icon_val

        # Preserve any other existing keys not controlled by this UI so
        # external systems don't lose data.
        existing = topic.data_json if isinstance(topic.data_json, dict) else {}
        if isinstance(existing, dict):
            for k, v in existing.items():
                if k not in meta:
                    meta[k] = v

        topic.data_json = meta or None

        db.session.add(topic)
        db.session.commit()

        try:
            generate_lesson_topics_json(topic.lesson_id)
        except Exception:
            current_app.logger.exception('Failed to regen lesson topics json after update_topic')

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

        # remember lesson id to regenerate topics JSON after deletion
        lid_for_regen = topic.lesson_id
        db.session.delete(topic)
        db.session.commit()
        try:
            generate_lesson_topics_json(lid_for_regen)
        except Exception:
            current_app.logger.exception('Failed to regen lesson topics json after delete_topic')
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
    # On success, return JSON for XHR callers, otherwise redirect to lesson page
    try:
        is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json or request.headers.get('Accept', '').startswith('application/json')
        if is_xhr:
            try:
                # regenerate top-level courses file
                generate_courses_json()
            except Exception:
                current_app.logger.exception('Failed to regen courses.json after create_course')
            return jsonify({'success': True, 'id': course.id}), 201
        return redirect(url_for('admin_bp.lesson_page') + f'?course_id={course.id}')
    except Exception:
        # If something odd happens while preparing the response, fall back to redirect
        return redirect(url_for('admin_bp.lesson_page') + f'?course_id={getattr(course, "id", "")}')

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
        published_flag = data.get('published')

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
        # Allow callers to toggle published via update_course when provided
        if published_flag is not None:
            course.published = bool(published_flag) if not isinstance(published_flag, str) else published_flag.lower() in ('1','true','yes','on')

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
        try:
            # regenerate courses list and the affected course lessons file
            generate_courses_json()
            generate_course_lessons_json(course.id)
        except Exception:
            current_app.logger.exception('Failed to regen json after update_course')
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
    # Legacy lessons UI has been replaced by the richer Course Content Management page.
    # Keep this route as a simple redirect for any existing links or bookmarks.
    return redirect(url_for('admin_bp.all_courses_page'))


@admin_bp.route('/course-content', methods=['GET'])
def course_content_page():
    """Render the richer Course Content Management UI for a specific course.

    Optional query param: course_id (used by template/JS if needed).
    """
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

    course_id = request.args.get('course_id')

    course = None
    lessons_count = 0
    lessons_for_ui = []
    try:
        if course_id:
            cid = int(course_id)
            course = Course.query.get(cid)
            if course:
                try:
                    # Load lessons and topics for this course so the Course Content
                    # Management page can render real data instead of hard-coded
                    # sample lessons. Order lessons FIFO (oldest first).
                    lessons_q = (
                        Lesson.query
                        .filter_by(course_id=course.id)
                        .order_by(Lesson.created_at.asc())
                        .all()
                    )
                    from app.models import Topic, Card  # local import to avoid cycles

                    for l in lessons_q:
                        topics_q = Topic.query.filter_by(lesson_id=l.id).order_by(Topic.created_at.asc()).all()
                        topics_for_lesson = []
                        for t in topics_q:
                            data = t.data_json if isinstance(t.data_json, dict) else {}

                            # Count cards for this topic directly from the Card table
                            try:
                                topic_cards_count = Card.query.filter_by(topic_id=t.id).count()
                            except Exception:
                                topic_cards_count = 0

                            topics_for_lesson.append({
                                'id': t.id,
                                'title': t.title,
                                'description': (data.get('description') if isinstance(data, dict) else '') or '',
                                'estimated_time': (data.get('estimated_time') if isinstance(data, dict) else None),
                                'difficulty': (data.get('difficulty') if isinstance(data, dict) else None) or 'medium',
                                'order': (data.get('order') if isinstance(data, dict) else None),
                                # Use a proper light-bulb emoji as the default icon
                                'icon': (data.get('icon') if isinstance(data, dict) else None) or '💡',
                                'cards_count': topic_cards_count,
                            })

                        meta = l.content_json if isinstance(l.content_json, dict) else {}
                        order_val = None
                        if isinstance(meta, dict) and meta.get('order') is not None:
                            try:
                                order_val = int(meta.get('order'))
                            except Exception:
                                order_val = meta.get('order')

                        prerequisite_val = None
                        if isinstance(meta, dict) and meta.get('prerequisite') is not None:
                            prerequisite_val = meta.get('prerequisite')

                        lessons_for_ui.append({
                            'id': l.id,
                            'title': l.title,
                            'description': l.description or '',
                            'duration': l.duration,
                            'level': l.level or '',
                            'order': order_val,
                            'prerequisite': prerequisite_val,
                            'topics': topics_for_lesson,
                        })

                    lessons_count = len(lessons_for_ui)
                except Exception:
                    lessons_count = 0
    except Exception:
        course = None
        lessons_count = 0
        lessons_for_ui = []

    return render_template(
        'Course-Content-Management.html',
        user=user,
        active='course-content',
        course=course,
        lessons_count=lessons_count,
        lessons_for_ui=lessons_for_ui,
    )


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
    # treat duration/estimated_time as the same logical field
    duration = data.get('duration') or data.get('lessonDuration') or data.get('estimated_time') or data.get('estimatedTime')
    level = data.get('level') or data.get('lessonLevel')
    objectives = data.get('objectives') or data.get('lessonObjectives')
    lesson_order = data.get('order') or data.get('lesson_order') or data.get('lessonOrder')
    prerequisite = data.get('prerequisite') or data.get('lessonPrerequisite') or data.get('prerequisiteInput')

    if not title or not course_id:
        flash('Missing title or course_id for lesson creation', 'error')
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "missing title or course_id"}, 400
        return redirect(url_for('admin_bp.lesson_page'))

    try:
        # If no explicit order provided, compute next order based on existing lessons in the course
        if (lesson_order is None or str(lesson_order).strip() == '') and course_id:
            try:
                existing_lessons = Lesson.query.filter_by(course_id=int(course_id)).all()
                max_order = 0
                for l in existing_lessons:
                    meta = l.content_json if isinstance(l.content_json, dict) else {}
                    if isinstance(meta, dict) and meta.get('order') is not None:
                        try:
                            val = int(meta.get('order'))
                        except Exception:
                            continue
                        if val > max_order:
                            max_order = val
                # fallback: if no orders present, use count
                if max_order == 0 and existing_lessons:
                    max_order = len(existing_lessons)
                lesson_order = max_order + 1
            except Exception:
                lesson_order = None

        # Package lesson metadata into content_json so that all attributes visible
        # in the admin UI are also represented in JSON. We still avoid legacy
        # duplicates like lesson_order/prerequisites keys.
        content = {}
        if description:
            content['description'] = description
        if duration:
            try:
                parsed_dur = int(duration)
            except Exception:
                parsed_dur = duration
            # store both duration and estimated_time for consumers that use either
            content['duration'] = parsed_dur
            content['estimated_time'] = parsed_dur
        if level:
            content['level'] = level
        if objectives:
            content['objectives'] = objectives
        if lesson_order is not None and lesson_order != '':
            try:
                parsed_order = int(lesson_order)
            except Exception:
                parsed_order = lesson_order
            # single canonical order key
            content['order'] = parsed_order
        if prerequisite:
            # single canonical prerequisite key
            content['prerequisite'] = prerequisite

        # populate convenience columns for easier querying from admin UI
        lesson = Lesson(
            title=title.strip(),
            course_id=int(course_id),
            content_json=content if content else None,
            description=description if description else None,
            duration=(int(duration) if duration and str(duration).isdigit() else None),
            level=(level if level else None),
            objectives=(objectives if objectives else None)
        )
        db.session.add(lesson)
        db.session.commit()
        try:
            generate_course_lessons_json(lesson.course_id)
        except Exception:
            current_app.logger.exception('Failed to regen lessons json after create_lesson')
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
    # duration may come from 'duration' or from an 'estimated_time' style field
    duration = data.get('duration') or data.get('lessonDuration') or data.get('estimated_time') or data.get('estimatedTime')
    level = data.get('level') or data.get('lessonLevel')
    objectives = data.get('objectives') or data.get('lessonObjectives')
    lesson_order = data.get('order') or data.get('lesson_order') or data.get('lessonOrder')
    prerequisite = data.get('prerequisite') or data.get('lessonPrerequisite') or data.get('prerequisiteInput')

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

        # Rebuild content_json so that attributes visible in the admin UI are
        # mirrored into JSON as well. This keeps JSON-based consumers in sync.
        meta = {}
        if description is not None:
            meta['description'] = description
        if duration is not None and str(duration).isdigit():
            try:
                parsed_dur = int(duration)
            except Exception:
                parsed_dur = duration
            meta['duration'] = parsed_dur
            meta['estimated_time'] = parsed_dur
        if level is not None:
            meta['level'] = level
        if objectives is not None:
            meta['objectives'] = objectives
        if prerequisite is not None:
            meta['prerequisite'] = prerequisite
        if lesson_order is not None and lesson_order != '':
            try:
                parsed_order = int(lesson_order)
            except Exception:
                parsed_order = lesson_order
            meta['order'] = parsed_order

        # if there was previous JSON, preserve any unknown keys that admin UI
        # does not control, so other systems don't lose data
        existing = lesson.content_json if isinstance(lesson.content_json, dict) else {}
        if isinstance(existing, dict):
            for k, v in existing.items():
                if k not in meta:
                    meta[k] = v

        lesson.content_json = meta or None

        db.session.commit()
        try:
            generate_course_lessons_json(lesson.course_id)
        except Exception:
            current_app.logger.exception('Failed to regen lessons json after update_lesson')
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
        try:
            # regenerate course lessons file for the course (if we can discover it)
            # best-effort: try to regen all
            generate_all_jsons()
        except Exception:
            current_app.logger.exception('Failed to regen json after delete_lesson')
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
    session.pop('admin_role', None)
    session.pop('admin_user_kind', None)
    flash('Logged out', 'info')
    # redirect to the site root (home endpoint)
    return redirect(url_for('home'))


@admin_bp.route('/cards_index', methods=['GET'])
def cards_index():
    # Optionally, require admin session here if needed
    lesson_id = request.args.get('lesson_id')
    topic_id = request.args.get('topic_id')
    display_order = request.args.get('display_order')
    return render_template('cards_index.html', lesson_id=lesson_id, topic_id=topic_id, display_order=display_order)
