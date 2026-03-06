# app/routes/api.py

"""
Mobile/Student API endpoints for EduSaint Flutter App
Base URL: https://byte.edusaint.in/api/v1
"""

from flask import Blueprint, request, jsonify, current_app, send_from_directory
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    verify_jwt_in_request
)
from app.extensions import db
from app.models import User, Course, Lesson, Topic, Student
from app.api.cards import _extract_r2_keys_from_image_url
from r2_client import s3, R2_BUCKET
from sqlalchemy import or_, text, func
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from app.utils.emailer import send_email
import traceback
import os
from app.utils.dynamic_json import generate_students_json
from app.utils.dynamic_json import (
    generate_user_progress_json,
    generate_courses_json,
    generate_course_lessons_json,
    generate_user_profile_json,
    generate_user_notifications_json,
)

# Create blueprint
# Use a distinct internal name to avoid colliding with `app.api.bp`
api_bp = Blueprint('routes_api', __name__, url_prefix='/api/v1')


# In-memory store for student password reset OTPs.
# NOTE: This is suitable for single-process deployments and development.
# For production, prefer a persistent store (DB/Redis) instead.
_STUDENT_RESET_OTP = {}

# Update a card by ID
@api_bp.route('/cards/<int:card_id>', methods=['PUT'])
def update_card(card_id):
    from app.models import Card
    from app.extensions import db
    data = request.get_json(silent=True) or {}
    card = Card.query.get(card_id)
    if not card:
        return jsonify({'success': False, 'error': 'Card not found'}), 404
    # Update fields if provided
    if 'title' in data:
        card.title = data['title']
    if 'card_type' in data:
        card.card_type = data['card_type']
    if 'type' in data:
        card.card_type = data['type']
    if 'display_order' in data:
        try:
            card.display_order = int(data['display_order'])
        except (TypeError, ValueError):
            pass
    db.session.commit()
    # Reuse the shared serializer so the update response matches GET payloads
    card_payload = serialize_card(card)
    return jsonify({'success': True, 'card': card_payload}), 200

# Delete a card by ID
@api_bp.route('/cards/<int:card_id>', methods=['DELETE'])
@jwt_required()
def delete_card(card_id):
    from app.models import Card
    from app.extensions import db
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    if not claims or claims.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    card = Card.query.get(card_id)
    if not card:
        return jsonify({'success': False, 'error': 'Card not found'}), 404

    # Best-effort: remove any associated images from R2 before deleting the card
    if R2_BUCKET:
        try:
            keys = _extract_r2_keys_from_image_url(card.image_url)
            for key in keys:
                try:
                    s3.delete_object(Bucket=R2_BUCKET, Key=key)
                except Exception:
                    current_app.logger.exception('Failed to delete R2 object for card %s key=%s', card.id, key)
        except Exception:
            current_app.logger.exception('Failed to derive R2 keys for card %s', card.id)

    try:
        db.session.delete(card)
        db.session.commit()
        return jsonify({'success': True, 'id': card_id}), 200
    except Exception as e:
        db.session.rollback()
        import traceback
        current_app.logger.exception('Failed to delete card')
        return jsonify({'success': False, 'error': 'Failed to delete card', 'details': str(e), 'trace': traceback.format_exc()}), 500

"""
Mobile/Student API endpoints for EduSaint Flutter App
Base URL: https://byte.edusaint.in/api/v1
"""

from flask import Blueprint, request, jsonify, current_app, send_from_directory
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    verify_jwt_in_request
)
from app.extensions import db
from app.models import User, Course, Lesson, Topic, Student
from sqlalchemy import or_, text
from datetime import datetime, timedelta
import traceback
import os
from app.utils.dynamic_json import generate_students_json
from app.utils.dynamic_json import (
    generate_user_progress_json,
    generate_courses_json,
    generate_course_lessons_json,
    generate_user_profile_json,
    generate_user_notifications_json,
)

# Create blueprint
# Use a distinct internal name to avoid colliding with `app.api.bp`
api_bp = Blueprint('routes_api', __name__, url_prefix='/api/v1')


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_profile_model():
    """Dynamically import Profile model to avoid circular imports"""
    try:
        from app.models import Profile
        return Profile
    except ImportError:
        return None


def get_student_model():
    """Dynamically import Student model if present."""
    try:
        from app.models import Student
        return Student
    except ImportError:
        return None


def resolve_user_and_student_ids():
    """Return tuple (user_id, student_id_or_None).

    - `user_id` is the id from the JWT identity (users.id).
    - `student_id_or_None` is the id from the `students` table when present.
    """
    try:
        current = get_jwt_identity()
    except Exception:
        return None, None

    uid = current.get('user_id') if isinstance(current, dict) else None
    # Prefer explicit student_id from identity if present
    sid = current.get('student_id') if isinstance(current, dict) else None
    if uid is not None:
        Student = get_student_model()
        if Student:
            try:
                s = Student.query.filter_by(user_id=uid).first()
                if s:
                    sid = s.id
                else:
                    # maybe students table uses same ids as users
                    s2 = Student.query.get(uid)
                    if s2:
                        sid = s2.id
            except Exception:
                sid = None

    return uid, sid


def get_enrollment_model():
    """Dynamically import Enrollment model"""
    try:
        from app.models import Enrollment
        return Enrollment
    except ImportError:
        return None


def get_progress_model():
    """Dynamically import Progress model"""
    try:
        from app.models import Progress
        return Progress
    except ImportError:
        return None


def generate_leaderboard_json(limit=10, write_file=True):
    """Compute leaderboard (total_time per user) and optionally write to
    `instance/dynamic_json/leaderboard.json`. Returns the leaderboard list.
    """
    try:
        from sqlalchemy import func, desc
        import json

        Progress = get_progress_model()
        if not Progress:
            return []

        rows = db.session.query(
            Progress.user_id,
            func.coalesce(func.sum(Progress.time_spent), 0).label('total_time'),
            func.count(Progress.id).label('lessons_count')
        ).group_by(Progress.user_id).order_by(desc('total_time')).limit(limit).all()

        board = []
        rank = 1
        Student = get_student_model()
        for r in rows:
            uid = int(r.user_id) if r.user_id is not None else None
            name = None
            email = None
            if Student and uid is not None:
                try:
                    s = Student.query.filter_by(user_id=uid).first() or Student.query.get(uid)
                    if s:
                        name = getattr(s, 'name', None)
                        email = getattr(s, 'email', None)
                except Exception:
                    pass
            if not name and uid is not None:
                try:
                    u = User.query.get(uid)
                    if u:
                        email = getattr(u, 'email', None)
                except Exception:
                    pass

            board.append({
                'rank': rank,
                'user_id': uid,
                'name': name,
                'email': email,
                'total_time': int(r.total_time) if r.total_time is not None else 0,
                'lessons_count': int(r.lessons_count)
            })
            rank += 1

        if write_file:
            try:
                dyn_dir = os.path.join(current_app.instance_path, 'dynamic_json')
                os.makedirs(dyn_dir, exist_ok=True)
                out_path = os.path.join(dyn_dir, 'leaderboard.json')
                with open(out_path, 'w', encoding='utf8') as fh:
                    json.dump({'leaderboard': board}, fh, ensure_ascii=False, indent=2)
            except Exception:
                current_app.logger.exception('Failed to write leaderboard.json')

        return board
    except Exception:
        current_app.logger.exception('Failed to generate leaderboard')
        return []


# ============================================================================
# SERIALIZERS (JSON HELPERS)
# ============================================================================

def serialize_course(course, lessons_count=None, enrolled_count=None, topics_count=None, cards_count=None):
    """Return a stable JSON representation for Course objects.

    Adds a few commonly-needed attributes so that mobile/web clients
    have richer metadata without needing additional queries.
    """
    if not course:
        return None

    created_at = course.created_at.isoformat() if getattr(course, 'created_at', None) else None

    payload = {
        # direct DB columns
        'id': course.id,
        'title': course.title,
        'description': course.description or '',
        'thumbnail_url': course.thumbnail_url,
        'thumbnail_asset_id': getattr(course, 'thumbnail_asset_id', None),
        'category': course.category,
        'class_name': getattr(course, 'class_name', None),
        'price': getattr(course, 'price', None),
        'published': getattr(course, 'published', None),
        'featured': getattr(course, 'featured', False),
        'duration_weeks': getattr(course, 'duration_weeks', None),
        'weekly_hours': getattr(course, 'weekly_hours', None),
        'difficulty': getattr(course, 'difficulty', None),
        'stream': getattr(course, 'stream', None),
        'tags': getattr(course, 'tags', None),
        'created_at': created_at,
    }

    if lessons_count is not None:
        # snake_case + camelCase for convenience
        payload['total_lessons'] = int(lessons_count)
        payload['totalLessons'] = int(lessons_count)
    if enrolled_count is not None:
        payload['enrolled_count'] = int(enrolled_count)
    if topics_count is not None:
        payload['total_topics'] = int(topics_count)
        payload['totalTopics'] = int(topics_count)
    if cards_count is not None:
        payload['total_cards'] = int(cards_count)
        payload['totalCards'] = int(cards_count)

    return payload


def serialize_lesson(lesson, topics_count=None, cards_count=None):
    """JSON representation for Lesson objects used across lesson APIs."""
    if not lesson:
        return None

    created_at = lesson.created_at.isoformat() if getattr(lesson, 'created_at', None) else None

    # derive ordering, icon, and rich description from content_json when present
    meta = lesson.content_json if isinstance(getattr(lesson, 'content_json', None), dict) else {}
    order_val = None
    # estimated_time in JSON should mirror DB column `duration`
    estimated_time = getattr(lesson, 'duration', None)
    meta_description = None
    meta_icon = None
    if isinstance(meta, dict):
        if meta.get('order') is not None:
            try:
                order_val = int(meta.get('order'))
            except Exception:
                order_val = meta.get('order')
        meta_description = meta.get('description')
        meta_icon = meta.get('icon')

    payload = {
        # direct DB columns
        'id': lesson.id,
        'course_id': lesson.course_id,
        'title': lesson.title,
        'content_json': getattr(lesson, 'content_json', None),
        # prefer description from content_json, fall back to column
        'description': meta_description or (lesson.description or ''),
        'duration': getattr(lesson, 'duration', None),
        'level': getattr(lesson, 'level', None),
        'objectives': getattr(lesson, 'objectives', None),
        'content_version': getattr(lesson, 'content_version', None),
        'created_at': created_at,
        # derived fields
        'order': order_val,
        'estimated_time': estimated_time,
        'icon': meta_icon,
    }

    if topics_count is not None:
        payload['topics_count'] = int(topics_count)
        payload['topicCount'] = int(topics_count)
    if cards_count is not None:
        payload['cardCount'] = int(cards_count)

    return payload


def _topic_base_dict(topic):
    """Helper to extract common Topic fields from data_json."""
    if not topic:
        return None

    raw_data = getattr(topic, 'data_json', None)
    data = raw_data if isinstance(raw_data, dict) else {}
    created_at = topic.created_at.isoformat() if getattr(topic, 'created_at', None) else None

    return {
        # direct DB columns
        'id': topic.id,
        'lesson_id': topic.lesson_id,
        'title': topic.title,
        'data_json': raw_data,
        'created_at': created_at,
        # convenient derived fields from data_json
        'content_type': data.get('type', 'text'),
        'content': data.get('content', ''),
        'description': data.get('description', ''),
        'duration': data.get('duration', 2),
        'order': data.get('order', 0),
        'estimated_time': data.get('estimated_time'),
        'difficulty': data.get('difficulty'),
    }


def serialize_topic(topic, include_lesson_order=False, include_card_count=True):
    """JSON representation for Topic objects.

    When include_lesson_order is True, attempts to enrich output with the
    lesson display order (from Lesson.content_json['order']) used in admin UI.
    """
    base = _topic_base_dict(topic)
    if not base:
        return None

    if include_lesson_order:
        try:
            from app.models import Lesson  # local import to avoid cycles
            lesson = Lesson.query.get(topic.lesson_id) if topic.lesson_id else None
            meta = lesson.content_json if (lesson and isinstance(lesson.content_json, dict)) else {}
            lesson_order = None
            if isinstance(meta, dict) and meta.get('order') is not None:
                try:
                    lesson_order = int(meta.get('order'))
                except Exception:
                    lesson_order = meta.get('order')
            base['lesson_order'] = lesson_order
        except Exception:
            # If anything fails here, skip lesson_order but keep other fields
            base['lesson_order'] = None

    # Optionally enrich with per-topic card count
    if include_card_count:
        try:
            from app.models import Card
            count = Card.query.filter_by(topic_id=topic.id).count()
            base['cardCount'] = int(count)
        except Exception:
            # If cards table/model not available, just omit cardCount
            base['cardCount'] = 0

    return base


def serialize_card(card):
    """JSON representation for Card objects used in topic/card APIs."""
    if not card:
        return None

    raw_data = getattr(card, 'data_json', None)
    data = raw_data if isinstance(raw_data, dict) else {}
    created_at = card.created_at.isoformat() if getattr(card, 'created_at', None) else None
    updated_at = card.updated_at.isoformat() if getattr(card, 'updated_at', None) else None

    return {
        # direct DB columns
        'id': card.id,
        'topic_id': card.topic_id,
        'lesson_id': card.lesson_id,
        'card_type': card.card_type,
        'title': card.title,
        'data_json': raw_data,
        'display_order': card.display_order,
        'created_by': getattr(card, 'created_by', None),
        'created_at': created_at,
        'updated_at': updated_at,
        'published': getattr(card, 'published', False),
        # convenient/derived fields
        'type': card.card_type,
        'content': data.get('content', data),
        'data': data,
    }


# ============================================================================
# AUTHENTICATION APIs
# ============================================================================

@api_bp.route('/auth/register', methods=['POST'])
def register():
    """
    Register new student user
    
    Request Body:
    {
        "email": "student@test.com",
        "password": "pass123",
        "name": "Student Name",
        "role": "student"  (optional, defaults to student)
    }
    
    Response:
    {
        "success": true,
        "message": "User registered successfully",
        "user_id": 123
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        email = data.get('email')
        password = data.get('password')
        name = data.get('name', email.split('@')[0] if email else 'user')
        role = data.get('role', 'student')
        
        # Validation
        if not email or not password:
            return jsonify({
                'success': False,
                'error': 'Email and password are required'
            }), 400
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({
                'success': False,
                'error': 'Email already registered'
            }), 400
        
        user_id = None
        student_id = None

        if role == 'admin':
            # Admins are stored in users table
            user = User(email=email.strip(), role='admin')
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            user_id = user.id
        else:
            # Students are stored only in students table
            # Validate optional mobile (10 digits)
            mobile_in = data.get('mobile')
            mobile_val = None
            if mobile_in:
                m = str(mobile_in)
                if len(m) == 10 and m.isdigit():
                    mobile_val = m
                else:
                    return jsonify({'success': False, 'error': 'Mobile must be 10 digits'}), 400
            new_student = Student(
                name=name.strip(),
                email=email.strip(),
                # Store raw password in Student table (legacy behavior)
                # Consider hashing in future migrations
                password=password,
                syllabus=data.get('syllabus', ''),
                class_=data.get('class', ''),
                courses=data.get('courses', data.get('subjects', '')),
                second_language=data.get('second_language', ''),
                third_language=data.get('third_language', ''),
                mobile=mobile_val,
                date=datetime.utcnow()
            )
            db.session.add(new_student)
            db.session.flush()
            student_id = new_student.id
        
        db.session.commit()
        
        # Regenerate students JSON for cloud sync
        if role != 'admin':
            try:
                generate_students_json()
            except Exception as e:
                current_app.logger.exception('Failed to regenerate students.json after registration')
        
        # Create profile
        # Create profile only for admins (users table)
        if role == 'admin':
            Profile = get_profile_model()
            if Profile and user_id is not None:
                try:
                    profile = Profile(
                        user_id=user_id,
                        name=name.strip(),
                        email=email.strip()
                    )
                    db.session.add(profile)
                    db.session.commit()
                except Exception as e:
                    current_app.logger.error(f'Failed to create profile: {e}')
                    # Don't fail registration if profile creation fails
        
        # Return appropriate identifier depending on role
        payload = {
            'success': True,
            'message': 'User registered successfully'
        }
        if role == 'admin':
            payload['user_id'] = user_id
        else:
            payload['student_id'] = student_id
        return jsonify(payload), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Registration failed')
        return jsonify({
            'success': False,
            'error': 'Registration failed',
            'details': str(e) if current_app.debug else None
        }), 500


@api_bp.route('/auth/login', methods=['POST'])
def login():
    """
    Login user and return JWT token
    
    Request Body:
    {
        "email": "student@test.com",
        "password": "pass123"
    }
    
    Response:
    {
        "success": true,
        "access_token": "eyJhbG...",
        "refresh_token": "eyJhbG...",
        "user": {
            "id": 123,
            "email": "student@test.com",
            "name": "Student Name",
            "role": "student"
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        email = data.get('email')
        password = data.get('password')
        
        # Validation
        if not email or not password:
            return jsonify({
                'success': False,
                'error': 'Email and password are required'
            }), 400
        
        # Admin login via users table
        user = User.query.filter_by(email=email, role='admin').first()
        if user and user.check_password(password):
            name = email
            Profile = get_profile_model()
            if Profile:
                try:
                    profile = Profile.query.filter_by(user_id=user.id).first()
                    if profile:
                        name = profile.name
                except Exception:
                    pass
            identity = str(user.id)
            access_token = create_access_token(identity=identity)
            refresh_token = create_refresh_token(identity=identity)
            return jsonify({
                'success': True,
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'name': name,
                    'role': 'admin'
                }
            }), 200

        # Fallback: student login via students table
        s = Student.query.filter_by(email=email).first()
        if not s or (s.password or '') != (password or ''):
            return jsonify({
                'success': False,
                'error': 'Invalid credentials'
            }), 401

        identity = str(s.id)
        access_token = create_access_token(identity=identity)
        refresh_token = create_refresh_token(identity=identity)

        return jsonify({
            'success': True,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': {
                'id': s.id,
                'email': s.email,
                'name': s.name or s.email,
                'role': 'student'
            }
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Login failed')
        return jsonify({
            'success': False,
            'error': 'Login failed',
            'details': str(e) if current_app.debug else None
        }), 500


@api_bp.route('/auth/refresh-token', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """
    Refresh access token using refresh token
    
    Headers:
    Authorization: Bearer <refresh_token>
    
    Response:
    {
        "success": true,
        "access_token": "eyJhbG..."
    }
    """
    try:
        current_user = get_jwt_identity()
        new_access_token = create_access_token(identity=str(current_user))
        return jsonify({
            'success': True,
            'access_token': new_access_token
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Token refresh failed')
        return jsonify({
            'success': False,
            'error': 'Token refresh failed'
        }), 500


@api_bp.route('/auth/verify', methods=['GET'])
@jwt_required()
def verify_token():
    """
    Verify if current token is valid
    
    Headers:
    Authorization: Bearer <access_token>
    
    Response:
    {
        "success": true,
        "user": {
            "user_id": 123,
            "email": "student@test.com",
            "role": "student"
        }
    }
    """
    try:
        current_user = get_jwt_identity()
        
        return jsonify({
            'success': True,
            'user': current_user
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Token verification failed'
        }), 401


@api_bp.route('/auth/logout', methods=['POST'])
@jwt_required()
def logout():
    """
    Logout (client-side token deletion, optional server-side blacklist)
    
    Response:
    {
        "success": true,
        "message": "Logged out successfully"
    }
    """
    # In a simple JWT setup, logout is handled client-side by deleting the token
    # For token blacklisting, you'd add the token to a blacklist here
    
    return jsonify({
        'success': True,
        'message': 'Logged out successfully'
    }), 200


@api_bp.route('/auth/student/forgot-password', methods=['POST'])
def student_forgot_password():
    """Start student password reset via OTP (Flutter JSON API).

    Request JSON:
    {
      "email": "student@example.com"
    }

    Behavior:
    - Finds the student by email.
    - Generates a 4-digit OTP, stores only a hash + expiry in memory.
    - Sends the OTP to the student's email using the common emailer.
    - Returns a generic success message (does NOT return the OTP).
    """
    try:
        data = request.get_json(silent=True) or {}
        email_raw = (data.get('email') or '').strip()
        if not email_raw:
            return jsonify({'success': False, 'error': 'Email is required'}), 400

        email_norm = email_raw.lower()

        # Look up student by email (case-insensitive where supported)
        student = None
        try:
            student = Student.query.filter(func.lower(Student.email) == email_norm).first()
        except Exception:
            try:
                student = Student.query.filter(Student.email.ilike(email_norm)).first()
            except Exception:
                student = Student.query.filter_by(email=email_raw).first()

        if not student:
            return jsonify({'success': False, 'error': 'No student found with this email'}), 404

        # Optional: prevent reset for inactive accounts
        if getattr(student, 'status', None) and str(student.status) != 'active':
            return jsonify({'success': False, 'error': 'Account is not active'}), 400

        # Decide which email to send OTP to (prefer stored student email,
        # fall back to raw email from request)
        target_email = (student.email or email_raw).strip()

        # Generate 4-digit OTP
        import secrets
        otp = f"{secrets.randbelow(10000):04d}"
        expires_at = datetime.utcnow() + timedelta(minutes=10)

        # Store hashed OTP and expiry in memory keyed by student id
        _STUDENT_RESET_OTP[int(student.id)] = {
            'otp_hash': generate_password_hash(otp),
            'expires_at': expires_at,
            'email': target_email,
        }

        subject = 'EduSaint Student Password Reset OTP'
        body = (
            'Hi,\n\n'
            'Use the OTP below to reset your EduSaint password:\n\n'
            f'OTP: {otp}\n\n'
            'This OTP expires in 10 minutes.\n\n'
            'If you did not request this, please ignore this email.\n\n'
            'Regards,\n'
            'EduSaint\n'
        )

        app_obj = current_app._get_current_object()

        def _send_student_pwreset_email() -> None:
            try:
                with app_obj.app_context():
                    sent_ok, err = send_email(to_email=target_email, subject=subject, body=body)
                    if not sent_ok:
                        current_app.logger.warning(
                            'Student password reset OTP for %s is %s (email send failed: %s)',
                            email_norm,
                            otp,
                            err,
                        )
            except Exception:
                try:
                    with app_obj.app_context():
                        current_app.logger.exception('Failed to send student password reset OTP email')
                except Exception:
                    pass

        import threading
        threading.Thread(target=_send_student_pwreset_email, daemon=True).start()

        response_data = {
            'success': True,
            'message': 'OTP sent to registered email if the account exists',
            'expires_in': 10 * 60,
        }

        # In development, optionally expose the OTP in the response to make
        # testing faster. This should be disabled in production.
        try:
            if current_app.debug or current_app.config.get('RETURN_OTP_IN_RESPONSE'):
                response_data['otp'] = otp
        except Exception:
            # If for some reason app context/config isn't available, just skip
            # adding the debug field rather than failing the whole request.
            pass

        return jsonify(response_data), 200
    except Exception as e:
        current_app.logger.exception('Student forgot-password (OTP) API failed')
        return jsonify({
            'success': False,
            'error': 'Failed to start password reset',
            'details': str(e) if current_app.debug else None,
        }), 500


@api_bp.route('/auth/student/verify-otp', methods=['POST'])
def student_verify_otp():
    """Verify student password reset OTP without changing password.

    Request JSON:
    {
      "email": "student@example.com",
      "otp": "1234"
    }

    Behavior:
    - Finds the student by email.
    - Looks up the in-memory OTP entry for that student.
    - Checks expiry and compares the provided OTP against the stored hash.
    - Returns success if valid, otherwise an appropriate error.
    """
    try:
        data = request.get_json(silent=True) or {}
        email_raw = (data.get('email') or '').strip()
        otp = (data.get('otp') or '').strip()

        if not email_raw or not otp:
            return jsonify({'success': False, 'error': 'Email and OTP are required'}), 400

        email_norm = email_raw.lower()

        # Look up student by email (case-insensitive where supported)
        student = None
        try:
            student = Student.query.filter(func.lower(Student.email) == email_norm).first()
        except Exception:
            try:
                student = Student.query.filter(Student.email.ilike(email_norm)).first()
            except Exception:
                student = Student.query.filter_by(email=email_raw).first()

        if not student:
            return jsonify({'success': False, 'error': 'No student found with this email'}), 404

        info = _STUDENT_RESET_OTP.get(int(student.id)) or {}
        if not info:
            return jsonify({'success': False, 'error': 'No active OTP found. Please request a new one.'}), 400

        expires_at = info.get('expires_at')
        if not expires_at or datetime.utcnow() > expires_at:
            _STUDENT_RESET_OTP.pop(int(student.id), None)
            return jsonify({'success': False, 'error': 'OTP expired. Please request a new one.'}), 400

        otp_hash = str(info.get('otp_hash') or '')
        if not otp_hash or not check_password_hash(otp_hash, otp):
            return jsonify({'success': False, 'error': 'Invalid OTP'}), 400

        # Mark as verified for potential future flows, but do not clear OTP
        info['verified'] = True
        info['verified_at'] = datetime.utcnow()
        _STUDENT_RESET_OTP[int(student.id)] = info

        return jsonify({'success': True, 'message': 'OTP verified successfully'}), 200
    except Exception as e:
        current_app.logger.exception('Student verify-otp API failed')
        return jsonify({
            'success': False,
            'error': 'Failed to verify OTP',
            'details': str(e) if current_app.debug else None,
        }), 500


@api_bp.route('/auth/student/reset-password', methods=['POST'])
def student_reset_password():
    """Reset student password using email + OTP.

    Request JSON:
    {
      "email": "student@example.com",
      "otp": "1234",
      "new_password": "NewPass123",
      "confirm_password": "NewPass123" // optional; defaults to new_password
    }
    """
    try:
        data = request.get_json(silent=True) or {}
        email_raw = (data.get('email') or '').strip()
        otp = (data.get('otp') or '').strip()
        new_password = (data.get('new_password') or '').strip()
        confirm_password = (data.get('confirm_password') or new_password).strip()

        if not email_raw or not otp:
            return jsonify({'success': False, 'error': 'Email and OTP are required'}), 400
        if not new_password or not confirm_password:
            return jsonify({'success': False, 'error': 'New password and confirmation are required'}), 400
        if new_password != confirm_password:
            return jsonify({'success': False, 'error': 'Passwords do not match'}), 400
        if len(new_password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400

        email_norm = email_raw.lower()

        # Look up student again to find the id
        student = None
        try:
            student = Student.query.filter(func.lower(Student.email) == email_norm).first()
        except Exception:
            try:
                student = Student.query.filter(Student.email.ilike(email_norm)).first()
            except Exception:
                student = Student.query.filter_by(email=email_raw).first()

        if not student:
            return jsonify({'success': False, 'error': 'No student found with this email'}), 404

        info = _STUDENT_RESET_OTP.get(int(student.id)) or {}
        if not info:
            return jsonify({'success': False, 'error': 'No active OTP found. Please request a new one.'}), 400

        expires_at = info.get('expires_at')
        if not expires_at or datetime.utcnow() > expires_at:
            _STUDENT_RESET_OTP.pop(int(student.id), None)
            return jsonify({'success': False, 'error': 'OTP expired. Please request a new one.'}), 400

        # Enforce strict flow: forgot-password -> verify-otp -> reset-password
        # Require that the OTP was previously verified via /auth/student/verify-otp
        if not info.get('verified'):
            return jsonify({'success': False, 'error': 'OTP not verified yet. Please verify the OTP first.'}), 400

        otp_hash = str(info.get('otp_hash') or '')
        if not otp_hash or not check_password_hash(otp_hash, otp):
            return jsonify({'success': False, 'error': 'Invalid OTP'}), 400

        # All good: update password and clear OTP
        student.password = new_password
        db.session.commit()
        _STUDENT_RESET_OTP.pop(int(student.id), None)

        return jsonify({
            'success': True,
            'message': 'Password updated successfully',
        }), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Student reset-password (OTP) API failed')
        return jsonify({
            'success': False,
            'error': 'Failed to reset password',
            'details': str(e) if current_app.debug else None,
        }), 500


# ============================================================================
# NOTIFICATIONS APIs
# ============================================================================


@api_bp.route('/notifications', methods=['GET'])
def list_notifications():
    """List notifications for the current user.

    Query params:
    - unread=true  => only unread notifications
    """
    try:
        # Allow optional JWT; fallback to explicit user_id or recent in DEBUG
        try:
            verify_jwt_in_request(optional=True)
            current = get_jwt_identity()
        except Exception:
            current = None

        uid = None
        if isinstance(current, dict):
            uid = current.get('user_id')
        # If no JWT identity, allow specifying user_id via query param
        if not uid:
            q_uid = request.args.get('user_id')
            try:
                uid = int(q_uid) if q_uid else None
            except Exception:
                uid = None

        unread = request.args.get('unread')
        # Build a SELECT with only the current DB columns
        try:
            fields = ['id', 'title', 'message', 'category', 'target', 'status', 'scheduled_at', 'created_at']
            base_sql = 'SELECT ' + ', '.join(fields) + ' FROM notifications'
            sql = base_sql + ' ORDER BY created_at DESC'
            rows = []
            with db.engine.begin() as conn:
                rows = conn.execute(text(sql)).mappings().all()
            out = []
            for r in rows:
                rec = dict(r)
                # normalize created_at
                if rec.get('created_at') and hasattr(rec['created_at'], 'isoformat'):
                    rec['created_at'] = rec['created_at'].isoformat()
                filtered = {k: rec.get(k) for k in fields if k in rec}
                out.append(filtered)
        except Exception:
            current_app.logger.exception('Failed to list notifications (full)')
            return jsonify({'success': False, 'error': 'failed to list notifications'}), 500

        return jsonify({'success': True, 'notifications': out}), 200
    except Exception:
        current_app.logger.exception('Failed to list notifications')
        return jsonify({'success': False, 'error': 'failed to list notifications'}), 500


@api_bp.route('/notifications/<int:notification_id>', methods=['GET'])
def get_notification(notification_id):
    try:
        # Optional auth; if provided, enforce owner/admin; otherwise allow public read
        try:
            verify_jwt_in_request(optional=True)
            current = get_jwt_identity()
        except Exception:
            current = None
        uid = current.get('user_id') if isinstance(current, dict) else None
        role = current.get('role') if isinstance(current, dict) else None

        # Fetch full record via dynamic SELECT so legacy columns are included
        try:
            fields = ['id', 'title', 'body', 'data', 'is_read', 'created_at', 'user_id']
            try:
                from sqlalchemy import inspect as _inspect
                cols = {c['name'] for c in _inspect(db.engine).get_columns('notifications')}
                for extra in ('message', 'category', 'icon'):
                    if extra in cols and extra not in fields:
                        fields.append(extra)
            except Exception:
                pass
            sql = 'SELECT ' + ', '.join(fields) + ' FROM notifications WHERE id = :nid'
            with db.engine.begin() as conn:
                row = conn.execute(text(sql), {'nid': notification_id}).mappings().first()
        except Exception:
            current_app.logger.exception('Failed to get notification (full)')
            row = None

        if not row:
            return jsonify({'success': False, 'error': 'not found'}), 404

        # If JWT present, enforce owner/admin; otherwise allow read-only access
        nid_user = row.get('user_id') if isinstance(row, dict) else None
        if uid is not None or role is not None:
            if nid_user != uid and role != 'admin':
                return jsonify({'success': False, 'error': 'unauthorized'}), 403

        # Normalize types
        import json as _json
        rec = dict(row)
        if 'data' in rec:
            try:
                if isinstance(rec['data'], (str, bytes)):
                    rec['data'] = _json.loads(rec['data'])
            except Exception:
                pass
        if rec.get('created_at') and hasattr(rec['created_at'], 'isoformat'):
            rec['created_at'] = rec['created_at'].isoformat()
        rec['is_read'] = bool(rec.get('is_read', False))

        return jsonify({'success': True, 'notification': rec}), 200
    except Exception:
        current_app.logger.exception('Failed to get notification')
        return jsonify({'success': False, 'error': 'failed to load notification'}), 500


@api_bp.route('/notifications', methods=['POST'])
def create_notification():
    """Create notifications. Admin-only.

    Body schema examples:
    - single user: {"user_id": 3, "title": "Hi", "body": "...", "data": {}}
    - multiple users: {"user_ids": [1,2,3], "title": "Update", "body": "..."}
    """
    try:
        data = request.get_json(silent=True) or {}
        title = data.get('title')
        body = data.get('body')
        payload = data.get('data')
        uids = []
        if 'user_ids' in data and isinstance(data.get('user_ids'), list):
            uids = [int(x) for x in data.get('user_ids') if x]
        elif 'user_id' in data and data.get('user_id'):
            uids = [int(data.get('user_id'))]

        if not title or not uids:
            return jsonify({'success': False, 'error': 'title and user_id(s) required'}), 400

        from app.models import Notification
        created = []
        for u in uids:
            n = Notification(user_id=u, title=title, body=body, data=payload)
            db.session.add(n)
            created.append(u)
        db.session.commit()

        # Regenerate per-user notifications JSON for cloud clients
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


@api_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
def mark_notification_read(notification_id):
    try:
        from app.models import Notification
        n = Notification.query.get(notification_id)
        if not n:
            return jsonify({'success': False, 'error': 'not found'}), 404
        n.is_read = True
        db.session.commit()
        # regenerate notifications json for the user
        try:
            if hasattr(n, 'user_id') and n.user_id:
                generate_user_notifications_json(int(n.user_id))
        except Exception:
            current_app.logger.exception('Failed to regen notifications json after mark read for user')
        return jsonify({'success': True}), 200
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to mark notification read')
        return jsonify({'success': False, 'error': 'failed to mark read'}), 500


@api_bp.route('/notifications/<int:notification_id>', methods=['DELETE'])
def delete_notification(notification_id):
    try:
        from app.models import Notification
        n = Notification.query.get(notification_id)
        if not n:
            return jsonify({'success': False, 'error': 'not found'}), 404
        user_of_notification = getattr(n, 'user_id', None)
        db.session.delete(n)
        db.session.commit()
        # regenerate notifications json for the user
        try:
            if user_of_notification:
                generate_user_notifications_json(int(user_of_notification))
        except Exception:
            current_app.logger.exception('Failed to regen notifications json after delete for user')
        return jsonify({'success': True}), 200
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to delete notification')
        return jsonify({'success': False, 'error': 'failed to delete notification'}), 500


# ============================================================================
# COURSES APIs (Read-only for students)
# ============================================================================

@api_bp.route('/courses', methods=['GET'])
def get_courses():
    """
    Get all courses with optional filters
    
    Query Parameters:
    - limit: Number of results (default: 20)
    - offset: Pagination offset (default: 0)
    - category_id: Filter by category
    - level: beginner/intermediate/advanced
    - search: Search in title/description
    
    Response:
    {
        "success": true,
        "total": 45,
        "courses": [
            {
                "id": 1,
                "title": "Python Basics",
                "description": "Learn Python...",
                "category": "Programming",
                "thumbnail_url": "https://...",
                "level": "beginner",
                "duration": 120,
                "total_lessons": 15,
                "enrolled_count": 1250,
                "rating": 4.5
            },
            ...
        ]
    }
    """
    try:
        # Get query parameters
        limit = int(request.args.get('limit', 20))
        offset = int(request.args.get('offset', 0))
        category = request.args.get('category_id') or request.args.get('category')
        level = request.args.get('level')
        search = request.args.get('search', '').strip()
        
        # Build query
        query = Course.query.filter_by(published=True)
        
        # Apply filters
        if category:
            query = query.filter_by(category=category)
        
        if level:
            query = query.filter_by(difficulty=level)
        
        if search:
            search_pattern = f'%{search}%'
            query = query.filter(
                or_(
                    Course.title.ilike(search_pattern),
                    Course.description.ilike(search_pattern)
                )
            )
        
        # Get total count
        total = query.count()
        
        # Paginate
        courses = query.offset(offset).limit(limit).all()
        
        # Build response
        courses_list = []
        from app.models import Card
        for c in courses:
            # Collect all lessons for this course
            lessons = Lesson.query.filter_by(course_id=c.id).all()
            lesson_ids = [l.id for l in lessons]
            lessons_count = len(lessons)

            # Totals for topics and cards within this course
            total_topics = 0
            total_cards = 0
            if lesson_ids:
                try:
                    total_topics = Topic.query.filter(Topic.lesson_id.in_(lesson_ids)).count()
                except Exception:
                    total_topics = 0
                try:
                    total_cards = Card.query.filter(Card.lesson_id.in_(lesson_ids)).count()
                except Exception:
                    total_cards = 0

            # Get enrollment count (if model exists)
            enrolled_count = 0
            Enrollment = get_enrollment_model()
            if Enrollment:
                try:
                    enrolled_count = Enrollment.query.filter_by(course_id=c.id).count()
                except Exception:
                    enrolled_count = 0

            # Use shared serializer so all course APIs expose the same fields
            course_payload = serialize_course(
                c,
                lessons_count=lessons_count,
                enrolled_count=enrolled_count,
                topics_count=total_topics,
                cards_count=total_cards,
            )
            # Backwards-compatible rating placeholder
            course_payload['rating'] = 4.5
            courses_list.append(course_payload)

        return jsonify({
            'success': True,
            'total': total,
            # expose both keys for compatibility with older clients/tests
            'courses': courses_list,
            'data': courses_list,
            'pagination': {
                'limit': limit,
                'offset': offset,
                'has_next': (offset + limit) < total,
                'has_prev': offset > 0
            }
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Get courses failed')
        return jsonify({
            'success': False,
            'error': 'Failed to load courses'
        }), 500


@api_bp.route('/courses/<int:course_id>', methods=['GET'])
def get_course_detail(course_id):
    """
    Get single course with lessons
    
    Response:
    {
        "success": true,
        "course": {
            "id": 1,
            "title": "Python Basics",
            "description": "Complete Python course...",
            "category": "Programming",
            "thumbnail_url": "...",
            "level": "beginner",
            "duration": 120,
            "lessons": [
                {
                    "id": 101,
                    "title": "Introduction to Python",
                    "description": "...",
                    "duration": 15,
                    "topics_count": 5
                },
                ...
            ]
        }
    }
    """
    try:
        course = Course.query.get(course_id)
        
        if not course:
            return jsonify({
                'success': False,
                'error': 'Course not found'
            }), 404
        
        # Get lessons
        lessons = Lesson.query.filter_by(course_id=course_id).all()
        lessons_list = []
        from app.models import Card

        total_topics = 0
        total_cards = 0

        for l in lessons:
            topics_count = Topic.query.filter_by(lesson_id=l.id).count()
            card_count = Card.query.filter_by(lesson_id=l.id).count()
            total_topics += topics_count
            total_cards += card_count
            lessons_list.append(serialize_lesson(l, topics_count=topics_count, cards_count=card_count))

        course_payload = serialize_course(
            course,
            lessons_count=len(lessons_list),
            topics_count=total_topics,
            cards_count=total_cards,
        )
        course_payload['lessons'] = lessons_list

        return jsonify({
            'success': True,
            'course': course_payload
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Get course detail failed')
        return jsonify({
            'success': False,
            'error': 'Failed to load course'
        }), 500


@api_bp.route('/courses/category/<category_name>', methods=['GET'])
def get_courses_by_category(category_name):
    """
    Get all courses in a specific category
    
    Response: Same as /courses but filtered by category
    """
    try:
        limit = int(request.args.get('limit', 20))
        offset = int(request.args.get('offset', 0))
        
        query = Course.query.filter_by(category=category_name, published=True)
        
        total = query.count()
        courses = query.offset(offset).limit(limit).all()
        
        courses_list = []
        from app.models import Card
        for c in courses:
            lessons = Lesson.query.filter_by(course_id=c.id).all()
            lesson_ids = [l.id for l in lessons]
            lessons_count = len(lessons)

            total_topics = 0
            total_cards = 0
            if lesson_ids:
                try:
                    total_topics = Topic.query.filter(Topic.lesson_id.in_(lesson_ids)).count()
                except Exception:
                    total_topics = 0
                try:
                    total_cards = Card.query.filter(Card.lesson_id.in_(lesson_ids)).count()
                except Exception:
                    total_cards = 0

            courses_list.append(
                serialize_course(
                    c,
                    lessons_count=lessons_count,
                    topics_count=total_topics,
                    cards_count=total_cards,
                )
            )

        return jsonify({
            'success': True,
            'total': total,
            'category': category_name,
            'courses': courses_list,
            'data': courses_list,
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Get courses by category failed')
        return jsonify({
            'success': False,
            'error': 'Failed to load courses'
        }), 500


@api_bp.route('/courses/search', methods=['GET'])
def search_courses():
    """
    Search courses
    
    Query Parameters:
    - q: Search query (required)
    
    Response: Same as /courses
    """
    query_text = request.args.get('q', '').strip()
    
    if not query_text:
        return jsonify({
            'success': False,
            'error': 'Search query required'
        }), 400
    
    # Redirect to main courses endpoint with search parameter
    return get_courses()


# ============================================================================
# LESSONS APIs
# ============================================================================

@api_bp.route('/courses/<int:course_id>/lessons', methods=['GET'])
def get_course_lessons(course_id):
    """
    Get all lessons in a course
    
    Response:
    {
        "success": true,
        "lessons": [
            {
                "id": 101,
                "title": "Introduction to Python",
                "description": "...",
                "duration": 15,
                "level": "beginner",
                "topics_count": 5
            },
            ...
        ]
    }
    """
    try:
        course = Course.query.get(course_id)
        
        if not course:
            return jsonify({
                'success': False,
                'error': 'Course not found'
            }), 404
        
        lessons = Lesson.query.filter_by(course_id=course_id).all()
        lessons_list = []
        from app.models import Card

        for l in lessons:
            topics_count = Topic.query.filter_by(lesson_id=l.id).count()
            card_count = Card.query.filter_by(lesson_id=l.id).count()
            lessons_list.append(serialize_lesson(l, topics_count=topics_count, cards_count=card_count))

        return jsonify({
            'success': True,
            'course_id': course_id,
            'lessons': lessons_list
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Get lessons failed')
        return jsonify({
            'success': False,
            'error': 'Failed to load lessons'
        }), 500


@api_bp.route('/lessons/<int:lesson_id>', methods=['GET'])
def get_lesson_detail(lesson_id):
    """
    Get single lesson details
    
    Response:
    {
        "success": true,
        "lesson": {
            "id": 101,
            "course_id": 1,
            "title": "Introduction",
            "description": "...",
            "duration": 15,
            "topics_count": 5
        }
    }
    """
    try:
        lesson = Lesson.query.get(lesson_id)

        if not lesson:
            return jsonify({
                'success': False,
                'error': 'Lesson not found'
            }), 404
        from app.models import Card

        topics_count = Topic.query.filter_by(lesson_id=lesson_id).count()
        card_count = Card.query.filter_by(lesson_id=lesson_id).count()

        lesson_payload = serialize_lesson(lesson, topics_count=topics_count, cards_count=card_count)

        return jsonify({
            'success': True,
            'lesson': lesson_payload
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Get lesson detail failed')
        return jsonify({
            'success': False,
            'error': 'Failed to load lesson'
        }), 500


@api_bp.route('/courses/<int:course_id>/lessons/<int:lesson_id>', methods=['GET'])
def get_course_lesson_detail(course_id, lesson_id):
    """
    Nested lesson detail endpoint.
    Validates the lesson belongs to the given course.
    Returns the same payload as `get_lesson_detail`.
    """
    try:
        course = Course.query.get(course_id)
        if not course:
            return jsonify({'success': False, 'error': 'Course not found'}), 404

        lesson = Lesson.query.get(lesson_id)
        if not lesson or lesson.course_id != course_id:
            return jsonify({'success': False, 'error': 'Lesson not found in course'}), 404

        from app.models import Card
        topics_count = Topic.query.filter_by(lesson_id=lesson_id).count()
        card_count = Card.query.filter_by(lesson_id=lesson_id).count()
        lesson_payload = serialize_lesson(lesson, topics_count=topics_count, cards_count=card_count)
        return jsonify({
            'success': True,
            'lesson': lesson_payload
        }), 200
    except Exception:
        current_app.logger.exception('Get nested lesson detail failed')
        return jsonify({'success': False, 'error': 'Failed to load lesson'}), 500


@api_bp.route('/lessons/<int:lesson_id>/content', methods=['GET'])
def get_lesson_content(lesson_id):
    """
    Get lesson content (alias for get_lesson_topics)
    """
    return get_lesson_topics(lesson_id)


# ============================================================================
# TOPICS/LEARNING CARDS APIs
# ============================================================================

@api_bp.route('/lessons/<int:lesson_id>/topics', methods=['GET'])
def get_lesson_topics(lesson_id):
    """
    Get all topics (learning cards) in a lesson
    
    Response:
    {
        "success": true,
        "topics": [
            {
                "id": 501,
                "title": "What is Python?",
                "content_type": "text",
                "content": "Python is...",
                "description": "...",
                "duration": 2,
                "order": 1
            },
            ...
        ]
    }
    """
    try:
        lesson = Lesson.query.get(lesson_id)
        
        if not lesson:
            return jsonify({
                'success': False,
                'error': 'Lesson not found'
            }), 404
        
        topics = Topic.query.filter_by(lesson_id=lesson_id).order_by(Topic.id).all()
        topics_list = []

        for t in topics:
            topics_list.append(serialize_topic(t))

        return jsonify({
            'success': True,
            'lesson_id': lesson_id,
            'topics': topics_list
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Get topics failed')
        return jsonify({
            'success': False,
            'error': 'Failed to load topics'
        }), 500


@api_bp.route('/courses/<int:course_id>/lessons/<int:lesson_id>/topics', methods=['GET'])
def get_course_lesson_topics(course_id, lesson_id):
    """
    Get all topics for a lesson using nested course/lesson path.

    Validates that the lesson belongs to the given course.
    Returns the same payload shape as `get_lesson_topics`.
    """
    try:
        course = Course.query.get(course_id)
        if not course:
            return jsonify({'success': False, 'error': 'Course not found'}), 404

        lesson = Lesson.query.get(lesson_id)
        if not lesson or lesson.course_id != course_id:
            return jsonify({'success': False, 'error': 'Lesson not found in course'}), 404

        topics = Topic.query.filter_by(lesson_id=lesson_id).order_by(Topic.id).all()
        topics_list = [serialize_topic(t) for t in topics]

        return jsonify({'success': True, 'lesson_id': lesson_id, 'topics': topics_list}), 200
    except Exception:
        current_app.logger.exception('Get nested topics failed')
        return jsonify({'success': False, 'error': 'Failed to load topics'}), 500


@api_bp.route('/topics/<int:topic_id>', methods=['GET'])
def get_topic_detail(topic_id):
    """
    Get single topic detail
    
    Response:
    {
        "success": true,
        "topic": {
            "id": 501,
            "lesson_id": 101,
            "title": "What is Python?",
            "content_type": "text",
            "content": "...",
            "description": "...",
            "duration": 2
        }
    }
    """
    try:
        topic = Topic.query.get(topic_id)
        
        if not topic:
            return jsonify({
                'success': False,
                'error': 'Topic not found'
            }), 404

        topic_payload = serialize_topic(topic, include_lesson_order=True)

        return jsonify({
            'success': True,
            'topic': topic_payload
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Get topic detail failed')
        return jsonify({
            'success': False,
            'error': 'Failed to load topic'
        }), 500


@api_bp.route('/topics/<int:topic_id>/cards', methods=['GET'])
def get_topic_cards(topic_id):
    """
    Get topic cards (swipeable content)
    This is an alias for get_topic_detail for now
    In future, can expand to return multiple cards per topic
    """
    try:
        topic = Topic.query.get(topic_id)
        if not topic:
            return jsonify({'success': False, 'error': 'Topic not found'}), 404

        from app.models import Card
        # Fetch all published cards for this topic ordered by display_order then id
        cards_q = Card.query.filter_by(topic_id=topic_id, published=True).order_by(Card.display_order, Card.id).all()
        cards = [serialize_card(c) for c in cards_q]
        return jsonify({'success': True, 'count': len(cards), 'cards': cards}), 200
    except Exception:
        current_app.logger.exception('Get topic cards failed')
        return jsonify({'success': False, 'error': 'Failed to load cards'}), 500


@api_bp.route('/courses/<int:course_id>/lessons/<int:lesson_id>/topics/<int:topic_id>', methods=['GET'])
def get_course_lesson_topic_detail(course_id, lesson_id, topic_id):
    """
    Nested topic detail endpoint.
    Validates that lesson belongs to course and topic belongs to lesson.
    Returns same payload as `get_topic_detail`.
    """
    try:
        course = Course.query.get(course_id)
        if not course:
            return jsonify({'success': False, 'error': 'Course not found'}), 404

        lesson = Lesson.query.get(lesson_id)
        if not lesson or lesson.course_id != course_id:
            return jsonify({'success': False, 'error': 'Lesson not found in course'}), 404

        topic = Topic.query.get(topic_id)
        if not topic or topic.lesson_id != lesson_id:
            return jsonify({'success': False, 'error': 'Topic not found in lesson'}), 404

        topic_payload = serialize_topic(topic, include_lesson_order=True)
        return jsonify({
            'success': True,
            'topic': topic_payload
        }), 200
    except Exception:
        current_app.logger.exception('Get nested topic detail failed')
        return jsonify({'success': False, 'error': 'Failed to load topic'}), 500


@api_bp.route('/courses/<int:course_id>/lessons/<int:lesson_id>/topics/<int:topic_id>/cards', methods=['GET'])
def get_course_lesson_topic_cards(course_id, lesson_id, topic_id):
    """Mobile-focused endpoint to fetch cards for a topic.

    Looks up the topic by ``topic_id`` and ``lesson_id`` and then returns all
    published cards for that topic, ordered by ``display_order`` and
    ``created_at``. The response includes both ``cards`` and ``data`` keys for
    compatibility with different clients.
    """
    try:
        from app.models import Card

        # Ensure the topic exists and belongs to the given lesson
        topic = Topic.query.filter_by(id=topic_id, lesson_id=lesson_id).first()
        if not topic:
            return jsonify({'success': False, 'error': 'Topic not found'}), 404

        q = Card.query.filter_by(topic_id=topic_id, lesson_id=lesson_id, published=True)
        cards_q = q.order_by(Card.display_order, Card.created_at).all()
        cards = [serialize_card(c) for c in cards_q]

        # Expose both "cards" and "data" so older and newer clients work
        return jsonify({'success': True, 'count': len(cards), 'cards': cards, 'data': cards}), 200
    except Exception:
        current_app.logger.exception('Get nested topic cards failed')
        return jsonify({'success': False, 'error': 'Failed to load topic cards'}), 500


@api_bp.route('/courses/<int:course_id>/lessons/<int:lesson_id>/topics/<int:topic_id>/cards/<int:card_id>', methods=['GET'])
def get_course_lesson_topic_card_detail(course_id, lesson_id, topic_id, card_id):
    """
    Get a single card by id under nested course/lesson/topic path.
    Validates that the lesson belongs to the course, topic belongs to the lesson,
    and the card belongs to the topic (and optionally lesson).
    """
    try:
        course = Course.query.get(course_id)
        if not course:
            return jsonify({'success': False, 'error': 'Course not found'}), 404

        lesson = Lesson.query.get(lesson_id)
        if not lesson or lesson.course_id != course_id:
            return jsonify({'success': False, 'error': 'Lesson not found in course'}), 404

        topic = Topic.query.get(topic_id)
        if not topic or topic.lesson_id != lesson_id:
            return jsonify({'success': False, 'error': 'Topic not found in lesson'}), 404

        from app.models import Card
        card = Card.query.get(card_id)
        if not card or card.topic_id != topic_id:
            return jsonify({'success': False, 'error': 'Card not found in topic'}), 404

        card_payload = serialize_card(card)
        return jsonify({
            'success': True,
            'card': card_payload
        }), 200
    except Exception:
        current_app.logger.exception('Get nested card detail failed')
        return jsonify({'success': False, 'error': 'Failed to load card'}), 500


# ============================================================================
# CLASSES APIs (group courses by class/grade)
# ============================================================================

@api_bp.route('/classes', methods=['GET'])
def get_classes():
    """Return the list of available classes (grades).

    Currently this is derived from ``Course.class_name`` for all published
    courses. Each entry includes the class identifier and how many courses are
    available for that class.

    Response example:
    {
        "success": true,
        "classes": [
            {"id": "6", "name": "6", "courses_count": 4},
            {"id": "7", "name": "7", "courses_count": 3}
        ]
    }
    """
    try:
        from sqlalchemy import func

        # Look at all courses that have a non-null class_name, regardless of
        # published status, so that every class present in the database (e.g.
        # MariaDB) shows up in this list.
        rows = db.session.query(
            Course.class_name,
            func.count(Course.id)
        ).filter(
            Course.class_name.isnot(None)
        ).group_by(Course.class_name).order_by(Course.class_name).all()

        classes = []
        for class_name, cnt in rows:
            if not class_name:
                continue
            # Normalize whitespace in case values like "8 " exist in the DB
            normalized = str(class_name).strip()
            if not normalized:
                continue
            classes.append({
                'id': normalized,
                'name': normalized,
                'courses_count': int(cnt)
            })

        return jsonify({'success': True, 'classes': classes}), 200
    except Exception:
        current_app.logger.exception('Get classes failed')
        return jsonify({'success': False, 'error': 'Failed to load classes'}), 500


@api_bp.route('/classes/<class_id>', methods=['GET'])
def get_class_detail(class_id):
    """Return summary information for a given class/grade.

    This is a *class* detail endpoint, not a full course listing. It
    returns a small summary payload that includes the number of courses
    for this class and a lightweight list of those courses. For the full
    course list (with pagination metadata) use
    ``GET /api/v1/classes/<class_id>/courses`` instead.
    """
    try:
        from sqlalchemy import func
        # Count how many courses belong to this class (trimmed)
        total = Course.query.filter(
            Course.class_name.isnot(None),
            func.trim(Course.class_name) == str(class_id)
        ).count()

        return jsonify(
            {
                "success": True,
                "class": {
                    "id": str(class_id),
                    "name": str(class_id),
                    "courses_count": total,
                },
            }
        ), 200
    except Exception:
        current_app.logger.exception('Get class detail failed')
        return jsonify({'success': False, 'error': 'Failed to load class courses'}), 500


# ============================================================================
# CLASS-SCOPED NESTED COURSE/LESSON/TOPIC/CARD APIs
# ============================================================================

@api_bp.route('/classes/<class_id>/courses', methods=['GET'])
def get_class_courses(class_id):
    """List courses for a given class/grade.

    The JSON structure and pagination semantics mirror the
    ``/api/v1/courses`` endpoint from app.api.courses.list_courses, but
    results are filtered to courses whose ``class_name`` (trimmed)
    equals ``class_id``.

    Example: ``GET /api/v1/classes/8/courses``.
    """
    try:
        from sqlalchemy import func

        # Same pagination and basic filters as app.api.courses.list_courses
        try:
            page = int(request.args.get('page', 1))
            limit = int(request.args.get('limit', 20))
        except ValueError:
            page, limit = 1, 20

        q = Course.query

        # Optional title filter (matches list_courses)
        title = request.args.get('title')
        if title:
            q = q.filter(Course.title.ilike(f"%{title}%"))

        # Constrain to the requested class id (trimmed)
        q = q.filter(
            Course.class_name.isnot(None),
            func.trim(Course.class_name) == str(class_id)
        )

        # Paginate in the same way as list_courses
        items = q.order_by(Course.created_at.desc()).paginate(page=page, per_page=limit, error_out=False)

        from app.models import Card
        data = []
        for c in items.items:
            # Aggregate counts, mirroring list_courses
            lessons = Lesson.query.filter_by(course_id=c.id).all()
            lesson_ids = [l.id for l in lessons]
            total_lessons = len(lessons)

            total_topics = 0
            total_cards = 0
            if lesson_ids:
                try:
                    total_topics = Topic.query.filter(Topic.lesson_id.in_(lesson_ids)).count()
                except Exception:
                    total_topics = 0
                try:
                    total_cards = Card.query.filter(Card.lesson_id.in_(lesson_ids)).count()
                except Exception:
                    total_cards = 0

            data.append(
                {
                    "id": c.id,
                    "title": c.title,
                    "description": c.description,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "class_name": getattr(c, "class_name", None),
                    "category": getattr(c, "category", None),
                    "totalLessons": int(total_lessons),
                    "totalTopics": int(total_topics),
                    "totalCards": int(total_cards),
                }
            )

        return jsonify(
            {
                "success": True,
                "data": data,
                "meta": {
                    "page": items.page,
                    "pages": items.pages,
                    "total": items.total,
                },
            }
        ), 200
    except Exception:
        current_app.logger.exception('Get class courses failed')
        return jsonify({'success': False, 'error': 'Failed to load class courses'}), 500


@api_bp.route('/classes/<class_id>/courses/<int:course_id>', methods=['GET'])
def get_class_course_detail(class_id, course_id):
    """Get a single course under a specific class.

    This validates that the course belongs to the given class and then
    returns the same payload as the main ``/api/v1/courses/<id>`` endpoint
    (implemented in ``app.api.courses.get_course``).
    """
    from sqlalchemy import func
    from app.api.courses import get_course as api_get_course

    course = Course.query.filter(
        Course.id == course_id,
        Course.class_name.isnot(None),
        func.trim(Course.class_name) == str(class_id)
    ).first()
    if not course:
        return jsonify({'success': False, 'error': 'Course not found in class'}), 404

    # Delegate to the canonical course-detail API so the JSON structure is
    # identical to /api/v1/courses/<course_id>.
    return api_get_course(course_id)


@api_bp.route('/classes/<class_id>/courses/<int:course_id>/lessons', methods=['GET'])
def get_class_course_lessons(class_id, course_id):
    """List lessons for a course scoped by class.

    Example: ``GET /api/v1/classes/8/courses/4/lessons``.
    """
    from sqlalchemy import func
    from app.api.courses import get_course_lessons as api_get_course_lessons

    course = Course.query.filter(
        Course.id == course_id,
        Course.class_name.isnot(None),
        func.trim(Course.class_name) == str(class_id)
    ).first()
    if not course:
        return jsonify({'success': False, 'error': 'Course not found in class'}), 404

    # Delegate to the canonical lessons-list API so the JSON structure is
    # identical to /api/v1/courses/<course_id>/lessons.
    return api_get_course_lessons(course_id)


@api_bp.route('/classes/<class_id>/courses/<int:course_id>/lessons/<int:lesson_id>', methods=['GET'])
def get_class_course_lesson_detail(class_id, course_id, lesson_id):
    """Get a single lesson under a specific class and course.

    Mirrors ``get_course_lesson_detail`` but with an additional class check.
    """
    from sqlalchemy import func

    course = Course.query.filter(
        Course.id == course_id,
        Course.class_name.isnot(None),
        func.trim(Course.class_name) == str(class_id)
    ).first()
    if not course:
        return jsonify({'success': False, 'error': 'Course not found in class'}), 404

    return get_course_lesson_detail(course_id, lesson_id)


@api_bp.route('/classes/<class_id>/courses/<int:course_id>/lessons/<int:lesson_id>/topics', methods=['GET'])
def get_class_course_lesson_topics(class_id, course_id, lesson_id):
    """List topics for a lesson under class + course.

    Example: ``GET /api/v1/classes/8/courses/4/lessons/9/topics``.
    """
    from sqlalchemy import func

    course = Course.query.filter(
        Course.id == course_id,
        Course.class_name.isnot(None),
        func.trim(Course.class_name) == str(class_id)
    ).first()
    if not course:
        return jsonify({'success': False, 'error': 'Course not found in class'}), 404

    return get_course_lesson_topics(course_id, lesson_id)


@api_bp.route('/classes/<class_id>/courses/<int:course_id>/lessons/<int:lesson_id>/topics/<int:topic_id>', methods=['GET'])
def get_class_course_lesson_topic_detail(class_id, course_id, lesson_id, topic_id):
    """Get topic details under class + course + lesson.
    """
    from sqlalchemy import func

    course = Course.query.filter(
        Course.id == course_id,
        Course.class_name.isnot(None),
        func.trim(Course.class_name) == str(class_id)
    ).first()
    if not course:
        return jsonify({'success': False, 'error': 'Course not found in class'}), 404

    return get_course_lesson_topic_detail(course_id, lesson_id, topic_id)


@api_bp.route('/classes/<class_id>/courses/<int:course_id>/lessons/<int:lesson_id>/topics/<int:topic_id>/cards', methods=['GET'])
def get_class_course_lesson_topic_cards(class_id, course_id, lesson_id, topic_id):
    """List cards for a topic under class + course + lesson.
    """
    from sqlalchemy import func

    course = Course.query.filter(
        Course.id == course_id,
        Course.class_name.isnot(None),
        func.trim(Course.class_name) == str(class_id)
    ).first()
    if not course:
        return jsonify({'success': False, 'error': 'Course not found in class'}), 404

    return get_course_lesson_topic_cards(course_id, lesson_id, topic_id)


@api_bp.route('/classes/<class_id>/courses/<int:course_id>/lessons/<int:lesson_id>/topics/<int:topic_id>/cards/<int:card_id>', methods=['GET'])
def get_class_course_lesson_topic_card_detail(class_id, course_id, lesson_id, topic_id, card_id):
    """Get a single card under class + course + lesson + topic.
    """
    from sqlalchemy import func

    course = Course.query.filter(
        Course.id == course_id,
        Course.class_name.isnot(None),
        func.trim(Course.class_name) == str(class_id)
    ).first()
    if not course:
        return jsonify({'success': False, 'error': 'Course not found in class'}), 404

    return get_course_lesson_topic_card_detail(course_id, lesson_id, topic_id, card_id)


# ============================================================================
# CATEGORIES APIs
# ============================================================================

@api_bp.route('/categories', methods=['GET'])
def get_categories():
    """
    Get all course categories
    
    Response:
    {
        "success": true,
        "categories": [
            {
                "name": "Programming",
                "count": 25
            },
            ...
        ]
    }
    """
    try:
        from sqlalchemy import func
        
        # Group by category and count
        rows = db.session.query(
            Course.category,
            func.count(Course.id)
        ).filter(
            Course.published == True,
            Course.category.isnot(None)
        ).group_by(Course.category).all()
        
        categories = []
        for cat, cnt in rows:
            categories.append({
                'name': cat,
                'count': int(cnt)
            })
        
        return jsonify({
            'success': True,
            'categories': categories
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Get categories failed')
        return jsonify({
            'success': False,
            'error': 'Failed to load categories'
        }), 500


@api_bp.route('/categories/<int:category_id>', methods=['GET'])
def get_category(category_id):
    """
    Get single category details
    Note: This assumes categories will be a separate table in future
    For now, returns error as categories are just course.category field
    """
    return jsonify({
        'success': False,
        'error': 'Not implemented - categories are stored as course attributes'
    }), 501


# ============================================================================
# ENROLLMENT APIs
# ============================================================================

@api_bp.route('/students/enrollments', methods=['GET'])
@jwt_required()
def get_my_enrollments():
    """
    Get all courses the student is enrolled in
    
    Response:
    {
        "success": true,
        "enrollments": [
            {
                "course_id": 1,
                "course_title": "Python Basics",
                "thumbnail_url": "...",
                "enrolled_at": "2024-01-15T10:30:00",
                "progress_percent": 45,
                "completed_topics": 20,
                "total_topics": 45,
                "last_accessed": "2024-02-20T15:30:00"
            },
            ...
        ]
    }
    """
    try:
        # Resolve both user_id (users.id) and student_id (students.id) when available
        uid, sid = resolve_user_and_student_ids()
        # Use `sid` for enrollment lookups when available, otherwise fall back to uid
        student_id_for_enroll = sid or uid
        
        Enrollment = get_enrollment_model()
        
        if not Enrollment:
            # Return empty list if enrollment model doesn't exist yet
            return jsonify({
                'success': True,
                'enrollments': [],
                'message': 'Enrollment feature not yet available'
            }), 200
        
        enrollments = []
        try:
            # Try to find enrollments for student_id (students.id) and user_id (legacy)
            if student_id_for_enroll is not None:
                enrollments = Enrollment.query.filter_by(student_id=student_id_for_enroll, is_active=True).all()
            if not enrollments and uid is not None and student_id_for_enroll != uid:
                enrollments = Enrollment.query.filter_by(student_id=uid, is_active=True).all()
        except Exception:
            enrollments = []
        
        enrollments_list = []
        
        for e in enrollments:
            course = Course.query.get(e.course_id)
            if not course:
                continue
            
            # Calculate progress
            Progress = get_progress_model()
            total_topics = 0
            completed_topics = 0
            
            if Progress:
                # Get all topics in course
                lessons = Lesson.query.filter_by(course_id=e.course_id).all()
                for lesson in lessons:
                    topics = Topic.query.filter_by(lesson_id=lesson.id).all()
                    total_topics += len(topics)
                    
                    for topic in topics:
                        # Map topic-level progress to lesson-level Progress model
                        # find any Progress record for the lesson by this user
                        progress = Progress.query.filter_by(
                            user_id=uid,
                            lesson_id=lesson.id
                        ).first()
                        if progress:
                            completed_topics += 1
            
            progress_percent = 0
            if total_topics > 0:
                progress_percent = round((completed_topics / total_topics) * 100, 2)
            
            enrollments_list.append({
                'enrollment_id': e.id,
                'course_id': e.course_id,
                'course_title': course.title,
                'thumbnail_url': course.thumbnail_url,
                'enrolled_at': e.enrolled_at.isoformat() if getattr(e, 'enrolled_at', None) else None,
                'progress_percent': progress_percent,
                'completed_topics': completed_topics,
                'total_topics': total_topics,
                'last_accessed': e.last_accessed.isoformat() if e.last_accessed else None
            })
        
        return jsonify({
            'success': True,
            'enrollments': enrollments_list
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Get enrollments failed')
        return jsonify({
            'success': False,
            'error': 'Failed to load enrollments'
        }), 500


@api_bp.route('/enroll', methods=['POST'])
@jwt_required()
def enroll_course():
    """
    Enroll in a course
    
    Request Body:
    {
        "course_id": 1
    }
    
    Response:
    {
        "success": true,
        "message": "Enrolled successfully",
        "enrollment_id": 789
    }
    """
    try:
        uid, sid = resolve_user_and_student_ids()
        
        data = request.get_json()
        course_id = data.get('course_id')
        
        if not course_id:
            return jsonify({
                'success': False,
                'error': 'Course ID required'
            }), 400
        
        # Check if course exists
        course = Course.query.get(course_id)
        if not course:
            return jsonify({
                'success': False,
                'error': 'Course not found'
            }), 404
        
        Enrollment = get_enrollment_model()
        
        if not Enrollment:
            return jsonify({
                'success': False,
                'error': 'Enrollment feature not yet available'
            }), 501
        
        # Check if already enrolled
        existing = None
        try:
            if sid is not None:
                existing = Enrollment.query.filter_by(student_id=sid, course_id=course_id).first()
            if not existing and uid is not None:
                existing = Enrollment.query.filter_by(student_id=uid, course_id=course_id).first()
        except Exception:
            existing = None
        
        if existing:
            if existing.is_active:
                return jsonify({
                    'success': False,
                    'error': 'Already enrolled in this course'
                }), 400
            else:
                # Reactivate enrollment
                existing.is_active = True
                existing.last_accessed = datetime.utcnow()
                db.session.commit()
                
                return jsonify({
                    'success': True,
                    'message': 'Re-enrolled successfully',
                    'enrollment_id': existing.id
                }), 200
        
        # Create new enrollment
        enrollment = Enrollment(
            student_id=(sid or uid),
            course_id=course_id,
            enrolled_at=datetime.utcnow(),
            is_active=True,
            last_accessed=datetime.utcnow()
        )
        
        db.session.add(enrollment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Enrolled successfully',
            'enrollment_id': enrollment.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Enrollment failed')
        return jsonify({
            'success': False,
            'error': 'Failed to enroll'
        }), 500


@api_bp.route('/enroll/<int:course_id>', methods=['DELETE'])
@jwt_required()
def unenroll_course(course_id):
    """
    Unenroll from a course (soft delete)
    
    Response:
    {
        "success": true,
        "message": "Unenrolled successfully"
    }
    """
    try:
        uid, sid = resolve_user_and_student_ids()
        
        Enrollment = get_enrollment_model()
        
        if not Enrollment:
            return jsonify({
                'success': False,
                'error': 'Enrollment feature not yet available'
            }), 501
        
        enrollment = None
        try:
            if sid is not None:
                enrollment = Enrollment.query.filter_by(student_id=sid, course_id=course_id).first()
            if not enrollment and uid is not None:
                enrollment = Enrollment.query.filter_by(student_id=uid, course_id=course_id).first()
        except Exception:
            enrollment = None
        
        if not enrollment:
            return jsonify({
                'success': False,
                'error': 'Not enrolled in this course'
            }), 404
        
        # Soft delete
        enrollment.is_active = False
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Unenrolled successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Unenrollment failed')
        return jsonify({
            'success': False,
            'error': 'Failed to unenroll'
        }), 500


@api_bp.route('/enrollment/check/<int:course_id>', methods=['GET'])
@jwt_required()
def check_enrollment(course_id):
    """
    Check if user is enrolled in a course
    
    Response:
    {
        "success": true,
        "enrolled": true,
        "enrollment_id": 789
    }
    """
    try:
        uid, sid = resolve_user_and_student_ids()
        
        Enrollment = get_enrollment_model()
        
        if not Enrollment:
            return jsonify({
                'success': True,
                'enrolled': False,
                'message': 'Enrollment feature not yet available'
            }), 200
        
        enrollment = None
        try:
            if sid is not None:
                enrollment = Enrollment.query.filter_by(student_id=sid, course_id=course_id, is_active=True).first()
            if not enrollment and uid is not None:
                enrollment = Enrollment.query.filter_by(student_id=uid, course_id=course_id, is_active=True).first()
        except Exception:
            enrollment = None
        
        return jsonify({
            'success': True,
            'enrolled': enrollment is not None,
            'enrollment_id': enrollment.id if enrollment else None
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Check enrollment failed')
        return jsonify({
            'success': False,
            'error': 'Failed to check enrollment'
        }), 500


# ============================================================================
# PROGRESS TRACKING APIs
# ============================================================================

@api_bp.route('/students/progress', methods=['GET'])
@jwt_required()
def get_overall_progress():
    """
    Get student's overall learning progress
    
    Response:
    {
        "success": true,
        "progress": {
            "total_courses_enrolled": 5,
            "total_courses_completed": 2,
            "total_topics_completed": 120,
            "total_learning_time": 1800,
            "current_streak": 7
        }
    }
    """
    try:
        uid, sid = resolve_user_and_student_ids()
        
        Enrollment = get_enrollment_model()
        Progress = get_progress_model()
        
        # Calculate stats
        total_enrolled = 0
        total_completed = 0
        total_topics_completed = 0
        total_learning_time = 0
        
        if Enrollment:
            try:
                total_enrolled = Enrollment.query.filter_by(student_id=(sid or uid), is_active=True).count()
                total_completed = Enrollment.query.filter_by(student_id=(sid or uid), is_active=True).filter(Enrollment.completed_at.isnot(None)).count()
            except Exception:
                total_enrolled = 0
                total_completed = 0
        
        if Progress:
            # Progress model is lesson-level and uses users.id as user_id
            try:
                completed_progress = Progress.query.filter_by(user_id=uid).all()
                total_topics_completed = len(completed_progress)
                total_learning_time = sum(p.time_spent or 0 for p in completed_progress)
            except Exception:
                total_topics_completed = 0
                total_learning_time = 0
        
        return jsonify({
            'success': True,
            'progress': {
                'total_courses_enrolled': total_enrolled,
                'total_courses_completed': total_completed,
                'total_topics_completed': total_topics_completed,
                'total_learning_time': total_learning_time,
                'current_streak': 0  # Implement streak calculation
            }
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Get progress failed')
        return jsonify({
            'success': False,
            'error': 'Failed to load progress'
        }), 500


@api_bp.route('/students/<int:student_id>/courses-completed', methods=['GET'])
def get_student_courses_completed(student_id):
    """Return aggregated course completion stats for a student.

    Endpoint shape:
      GET /api/v1/students/{studentId}/courses-completed?view=day|month&year=2025|2024

    Response (placeholder example):
      {
        "success": true,
        "student_id": 1,
        "view": "day",
        "year": 2025,
        "data": [
          {"date": "2025-01-01", "completed": 2},
          {"date": "2025-01-02", "completed": 0}
        ]
      }

    Aggregation logic:
      - Uses the Enrollment model (if present).
      - Counts how many courses reached completed_at on each day or month
        of the given year for the specified student_id.
    """
    from datetime import datetime

    view = (request.args.get('view') or 'day').lower()
    if view not in ('day', 'month'):
        view = 'day'

    year_raw = request.args.get('year') or '2025'
    try:
        year = int(year_raw)
    except Exception:
        year = 2025

    if year not in (2024, 2025):
        year = 2025

    Enrollment = get_enrollment_model()
    if not Enrollment:
        # Enrollment table not available yet
        return jsonify({
            'success': True,
            'student_id': student_id,
            'view': view,
            'year': year,
            'data': []
        }), 200

    # Determine time window for the requested year
    try:
        start = datetime(year, 1, 1)
        end = datetime(year + 1, 1, 1)
    except Exception:
        # Fallback: no date filtering if datetime construction fails
        start = None
        end = None

    try:
        q = Enrollment.query.filter_by(student_id=student_id, is_active=True)
        # Only include enrollments that have been completed
        if getattr(Enrollment, 'completed_at', None) is not None:
            q = q.filter(Enrollment.completed_at.isnot(None))

            if start is not None and end is not None:
                q = q.filter(Enrollment.completed_at >= start, Enrollment.completed_at < end)

        enrollments = q.all()
    except Exception:
        current_app.logger.exception('Failed to load enrollments for courses-completed endpoint')
        enrollments = []

    # Aggregate completions per day or month
    buckets = {}
    for e in enrollments:
        completed_at = getattr(e, 'completed_at', None)
        if not completed_at:
            continue

        if view == 'day':
            key = completed_at.date().isoformat()
        else:  # month view
            key = completed_at.strftime('%Y-%m')

        buckets[key] = buckets.get(key, 0) + 1

    # Convert to sorted list of {date, completed} objects
    data = [
        {'date': k, 'completed': buckets[k]}
        for k in sorted(buckets.keys())
    ]

    return jsonify({
        'success': True,
        'student_id': student_id,
        'view': view,
        'year': year,
        'data': data
    }), 200


@api_bp.route('/students/progress/<int:course_id>', methods=['GET'])
@jwt_required()
def get_course_progress(course_id):
    """
    Get progress for a specific course
    
    Response:
    {
        "success": true,
        "progress": {
            "course_id": 1,
            "progress_percent": 45,
            "completed_topics": 20,
            "total_topics": 45,
            "time_spent": 600
        }
    }
    """
    try:
        uid, sid = resolve_user_and_student_ids()
        
        # Check if course exists
        course = Course.query.get(course_id)
        if not course:
            return jsonify({
                'success': False,
                'error': 'Course not found'
            }), 404
        
        Progress = get_progress_model()
        
        # Calculate progress
        total_topics = 0
        completed_topics = 0
        time_spent = 0
        
        if Progress:
            # Get all topics in course
            lessons = Lesson.query.filter_by(course_id=course_id).all()
            
            for lesson in lessons:
                topics = Topic.query.filter_by(lesson_id=lesson.id).all()
                total_topics += len(topics)
                
                for topic in topics:
                    # Map topic -> lesson progress: treat a Progress row for the
                    # lesson as the unit of completion. Use lesson_id from topic.
                    p = Progress.query.filter_by(
                        user_id=uid,
                        lesson_id=lesson.id
                    ).first()
                    if p:
                        completed_topics += 1
                        time_spent += p.time_spent or 0
        
        progress_percent = 0
        if total_topics > 0:
            progress_percent = round((completed_topics / total_topics) * 100, 2)
        
        return jsonify({
            'success': True,
            'progress': {
                'course_id': course_id,
                'progress_percent': progress_percent,
                'completed_topics': completed_topics,
                'total_topics': total_topics,
                'time_spent': time_spent
            }
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Get course progress failed')
        return jsonify({
            'success': False,
            'error': 'Failed to load progress'
        }), 500


@api_bp.route('/progress/update', methods=['POST'])
@jwt_required()
def update_progress():
    """
    Update learning progress (when topic viewed/completed)
    
    Request Body:
    {
        "topic_id": 502,
        "time_spent": 5,
        "completed": true
    }
    
    Response:
    {
        "success": true,
        "message": "Progress updated",
        "course_progress": 48
    }
    """
    try:
        uid, sid = resolve_user_and_student_ids()
        
        data = request.get_json()
        
        topic_id = data.get('topic_id')
        time_spent = data.get('time_spent', 0)

        # Accept either topic_id (will map to lesson) or lesson_id directly
        if not topic_id and not data.get('lesson_id'):
            return jsonify({
                'success': False,
                'error': 'topic_id or lesson_id required'
            }), 400
        
        Progress = get_progress_model()
        
        if not Progress:
            return jsonify({
                'success': False,
                'error': 'Progress tracking not yet available'
            }), 501
        
        # Check if progress record exists
        # Support either topic-level input (map to lesson) or lesson-level input
        lesson_id = None
        if 'lesson_id' in data and data.get('lesson_id'):
            lesson_id = data.get('lesson_id')
        else:
            # fallback to topic -> lesson mapping
            topic = Topic.query.get(topic_id)
            if topic:
                lesson_id = topic.lesson_id

        if not lesson_id:
            return jsonify({
                'success': False,
                'error': 'Lesson could not be determined from topic'
            }), 400

        # Check if progress record exists for (user, lesson)
        progress = Progress.query.filter_by(
            user_id=uid,
            lesson_id=lesson_id
        ).first()

        if progress:
            # Update existing
            if time_spent:
                progress.time_spent = (progress.time_spent or 0) + time_spent
            if 'score' in data and data.get('score') is not None:
                progress.score = data.get('score')
            if 'answers' in data and data.get('answers') is not None:
                progress.answers = data.get('answers')
        else:
            # Create new progress record (lesson-level)
            progress = Progress(
                user_id=uid,
                lesson_id=lesson_id,
                time_spent=time_spent,
                score=data.get('score'),
                answers=data.get('answers'),
                attempt_id=data.get('attempt_id'),
                created_at=datetime.utcnow()
            )
            db.session.add(progress)
        
        db.session.commit()
        try:
            generate_user_progress_json(uid)
        except Exception:
            current_app.logger.exception('Failed to regen user progress json after update_progress')
        try:
            # refresh leaderboard artifact when progress changes
            generate_leaderboard_json(write_file=True)
        except Exception:
            current_app.logger.exception('Failed to regen leaderboard json after update_progress')
        
        # Calculate course progress at lesson granularity
        # Determine lesson for the updated progress
        lesson = Lesson.query.get(lesson_id)
        course_progress = 0

        if lesson:
            lessons = Lesson.query.filter_by(course_id=lesson.course_id).all()
            total_lessons = len(lessons)
            completed_lessons = 0

            for l in lessons:
                p = Progress.query.filter_by(
                    user_id=uid,
                    lesson_id=l.id
                ).first()
                if p:
                    completed_lessons += 1

            if total_lessons > 0:
                course_progress = round((completed_lessons / total_lessons) * 100, 2)
        
        return jsonify({
            'success': True,
            'message': 'Progress updated',
            'course_progress': course_progress
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Update progress failed')
        return jsonify({
            'success': False,
            'error': 'Failed to update progress'
        }), 500





# ============================================================================
# SEARCH APIs
# ============================================================================

@api_bp.route('/search', methods=['GET'])
def global_search():
    """
    Global search across courses, lessons, topics
    
    Query Parameters:
    - q: Search query (required)
    - type: course/lesson/topic (optional)
    
    Response:
    {
        "success": true,
        "query": "python",
        "results": {
            "courses": [...],
            "lessons": [...],
            "topics": [...]
        }
    }
    """
    try:
        query_text = request.args.get('q', '').strip()
        result_type = request.args.get('type', '').strip().lower()
        
        if not query_text:
            return jsonify({
                'success': False,
                'error': 'Search query required'
            }), 400
        
        search_pattern = f'%{query_text}%'
        results = {}
        
        # Search courses
        if not result_type or result_type == 'course':
            courses = Course.query.filter(
                Course.published == True,
                or_(
                    Course.title.ilike(search_pattern),
                    Course.description.ilike(search_pattern)
                )
            ).limit(10).all()
            
            results['courses'] = [{
                'id': c.id,
                'title': c.title,
                'description': c.description,
                'type': 'course'
            } for c in courses]
        
        # Search lessons
        if not result_type or result_type == 'lesson':
            lessons = Lesson.query.filter(
                or_(
                    Lesson.title.ilike(search_pattern),
                    Lesson.description.ilike(search_pattern)
                )
            ).limit(10).all()
            
            results['lessons'] = [{
                'id': l.id,
                'title': l.title,
                'description': l.description,
                'course_id': l.course_id,
                'type': 'lesson'
            } for l in lessons]
        
        # Search topics
        if not result_type or result_type == 'topic':
            topics = Topic.query.filter(
                Topic.title.ilike(search_pattern)
            ).limit(10).all()
            
            results['topics'] = [{
                'id': t.id,
                'title': t.title,
                'lesson_id': t.lesson_id,
                'type': 'topic'
            } for t in topics]
        
        return jsonify({
            'success': True,
            'query': query_text,
            'results': results
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Search failed')
        return jsonify({
            'success': False,
            'error': 'Search failed'
        }), 500


# ============================================================================
# CLOUD FILES API
# ============================================================================

@api_bp.route('/cloud/<path:filename>', methods=['GET'])
def get_cloud_file(filename):
    """Serve dynamic JSON files generated by the backend.
    Files are stored under `instance/dynamic_json/`.
    """
    try:
        base = os.path.join(current_app.instance_path, 'dynamic_json')
        return send_from_directory(base, filename)
    except Exception:
        return jsonify({'success': False, 'error': 'File not found'}), 404


# ============================================================================
# SETTINGS APIs
# ============================================================================


@api_bp.route('/settings', methods=['GET'])
@jwt_required()
def get_my_settings():
    """Return per-user settings stored under `instance/settings/user_<id>_settings.json`.

    If no file exists, return sensible defaults (and profile/student info when available).
    """
    try:
        import json

        current = get_jwt_identity()
        uid = current.get('user_id') if isinstance(current, dict) else None
        if not uid:
            return jsonify({'success': False, 'error': 'invalid identity'}), 401

        settings_dir = os.path.join(current_app.instance_path, 'settings')
        os.makedirs(settings_dir, exist_ok=True)
        fname = os.path.join(settings_dir, f'user_{uid}_settings.json')

        if os.path.exists(fname):
            try:
                with open(fname, 'r', encoding='utf8') as fh:
                    data = json.load(fh)
                return jsonify({'success': True, 'settings': data}), 200
            except Exception:
                current_app.logger.exception('Failed to read settings file')
                return jsonify({'success': False, 'error': 'failed to load settings'}), 500

        # No explicit settings saved — build defaults from Student/Profile/User
        defaults = {
            'notifications': True,
            'dark_mode': False,
            'language': 'en',
            'preferences': {}
        }

        Student = get_student_model()
        if Student:
            try:
                s = Student.query.filter_by(user_id=uid).first() or Student.query.get(uid)
                if s:
                    defaults['display_name'] = getattr(s, 'name', None)
                    defaults['email'] = getattr(s, 'email', None)
            except Exception:
                pass
        else:
            Profile = get_profile_model()
            if Profile:
                try:
                    p = Profile.query.filter_by(user_id=uid).first()
                    if p:
                        defaults['display_name'] = getattr(p, 'name', None)
                        defaults['email'] = getattr(p, 'email', None)
                except Exception:
                    pass

        return jsonify({'success': True, 'settings': defaults}), 200
    except Exception:
        current_app.logger.exception('Get settings failed')
        return jsonify({'success': False, 'error': 'failed to load settings'}), 500


@api_bp.route('/settings', methods=['PUT', 'POST'])
@jwt_required()
def save_my_settings():
    """Persist the requesting user's settings to `instance/settings/`.

    Accepts arbitrary JSON payload; we don't enforce a schema here.
    """
    try:
        import json
        current = get_jwt_identity()
        uid = current.get('user_id') if isinstance(current, dict) else None
        if not uid:
            return jsonify({'success': False, 'error': 'invalid identity'}), 401

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'success': False, 'error': 'invalid payload'}), 400

        settings_dir = os.path.join(current_app.instance_path, 'settings')
        os.makedirs(settings_dir, exist_ok=True)
        fname = os.path.join(settings_dir, f'user_{uid}_settings.json')

        try:
            with open(fname, 'w', encoding='utf8') as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception:
            current_app.logger.exception('Failed to write settings file')
            return jsonify({'success': False, 'error': 'failed to save settings'}), 500

        # Mirror settings to dynamic_json for cloud consumption
        try:
            dyn_dir = os.path.join(current_app.instance_path, 'dynamic_json')
            os.makedirs(dyn_dir, exist_ok=True)
            out_path = os.path.join(dyn_dir, f'user_{uid}_settings.json')
            with open(out_path, 'w', encoding='utf8') as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception:
            current_app.logger.exception('Failed to mirror settings to dynamic_json')

        return jsonify({'success': True, 'settings': data}), 200
    except Exception:
        current_app.logger.exception('Save settings failed')
        return jsonify({'success': False, 'error': 'failed to save settings'}), 500


# ============================================================================
# LEADERBOARD APIs
# ============================================================================


@api_bp.route('/leaderboard', methods=['GET'])
def leaderboard():
    """Return a simple leaderboard of users sorted by total learning time.

    Query params:
    - limit (int, default 10)
    - period (optional): currently ignored (future: weekly/monthly)
    """
    try:
        # Generate leaderboard and persist to dynamic_json for client consumption
        limit = int(request.args.get('limit', 10))
        board = generate_leaderboard_json(limit=limit, write_file=True)
        return jsonify({'success': True, 'leaderboard': board}), 200
    except Exception:
        current_app.logger.exception('Leaderboard generation failed')
        return jsonify({'success': False, 'error': 'failed to generate leaderboard'}), 500


# ============================================================================
# HEALTH CHECK
# ============================================================================

@api_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint
    
    Response:
    {
        "status": "ok",
        "timestamp": "2024-11-23T10:30:00"
    }
    """
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0'
    }), 200


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@api_bp.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint not found'
    }), 404


@api_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500
