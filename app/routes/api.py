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
    get_jwt_identity
)
from app.extensions import db
from app.models import User, Course, Lesson, Topic, Student
from sqlalchemy import or_
from datetime import datetime
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
            new_student = Student(
                name=name.strip(),
                email=email.strip(),
                # Store raw password in Student table (legacy behavior)
                # Consider hashing in future migrations
                password=password,
                syllabus=data.get('syllabus', ''),
                class_=data.get('class', ''),
                subjects=data.get('subjects', ''),
                second_language=data.get('second_language', ''),
                third_language=data.get('third_language', ''),
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
            identity = {
                'user_id': user.id,
                'email': user.email,
                'role': 'admin'
            }
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

        identity = {
            'student_id': s.id,
            'email': s.email,
            'role': 'student'
        }
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
        new_access_token = create_access_token(identity=current_user)
        
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


# ============================================================================
# NOTIFICATIONS APIs
# ============================================================================


@api_bp.route('/notifications', methods=['GET'])
@jwt_required()
def list_notifications():
    """List notifications for the current user.

    Query params:
    - unread=true  => only unread notifications
    """
    try:
        current = get_jwt_identity()
        uid = current.get('user_id') if isinstance(current, dict) else None
        if not uid:
            return jsonify({'success': False, 'error': 'invalid identity'}), 401

        unread = request.args.get('unread')
        from app.models import Notification
        q = Notification.query.filter_by(user_id=uid)
        if unread and unread.lower() in ('1', 'true', 'yes'):
            q = q.filter_by(is_read=False)

        items = q.order_by(Notification.created_at.desc()).all()
        out = []
        for n in items:
            out.append({
                'id': n.id,
                'title': n.title,
                'body': n.body,
                'data': n.data,
                'is_read': bool(n.is_read),
                'created_at': n.created_at.isoformat() if getattr(n, 'created_at', None) else None
            })

        return jsonify({'success': True, 'notifications': out}), 200
    except Exception:
        current_app.logger.exception('Failed to list notifications')
        return jsonify({'success': False, 'error': 'failed to list notifications'}), 500


@api_bp.route('/notifications/<int:notification_id>', methods=['GET'])
@jwt_required()
def get_notification(notification_id):
    try:
        current = get_jwt_identity()
        uid = current.get('user_id') if isinstance(current, dict) else None
        role = current.get('role') if isinstance(current, dict) else None

        from app.models import Notification
        n = Notification.query.get(notification_id)
        if not n:
            return jsonify({'success': False, 'error': 'not found'}), 404

        # allow owner or admin
        if n.user_id != uid and role != 'admin':
            return jsonify({'success': False, 'error': 'unauthorized'}), 403

        return jsonify({'success': True, 'notification': {
            'id': n.id,
            'title': n.title,
            'body': n.body,
            'data': n.data,
            'is_read': bool(n.is_read),
            'created_at': n.created_at.isoformat() if getattr(n, 'created_at', None) else None
        }}), 200
    except Exception:
        current_app.logger.exception('Failed to get notification')
        return jsonify({'success': False, 'error': 'failed to load notification'}), 500


@api_bp.route('/notifications', methods=['POST'])
@jwt_required()
def create_notification():
    """Create notifications. Admin-only.

    Body schema examples:
    - single user: {"user_id": 3, "title": "Hi", "body": "...", "data": {}}
    - multiple users: {"user_ids": [1,2,3], "title": "Update", "body": "..."}
    """
    try:
        current = get_jwt_identity()
        role = current.get('role') if isinstance(current, dict) else None
        if role != 'admin':
            return jsonify({'success': False, 'error': 'forbidden'}), 403

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
@jwt_required()
def mark_notification_read(notification_id):
    try:
        current = get_jwt_identity()
        uid = current.get('user_id') if isinstance(current, dict) else None
        if not uid:
            return jsonify({'success': False, 'error': 'invalid identity'}), 401

        from app.models import Notification
        n = Notification.query.get(notification_id)
        if not n:
            return jsonify({'success': False, 'error': 'not found'}), 404
        if n.user_id != uid:
            return jsonify({'success': False, 'error': 'unauthorized'}), 403

        n.is_read = True
        db.session.commit()
        # regenerate notifications json for the user
        try:
            generate_user_notifications_json(int(uid))
        except Exception:
            current_app.logger.exception('Failed to regen notifications json after mark read for user %s', uid)
        return jsonify({'success': True}), 200
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to mark notification read')
        return jsonify({'success': False, 'error': 'failed to mark read'}), 500


@api_bp.route('/notifications/<int:notification_id>', methods=['DELETE'])
@jwt_required()
def delete_notification(notification_id):
    try:
        current = get_jwt_identity()
        uid = current.get('user_id') if isinstance(current, dict) else None
        role = current.get('role') if isinstance(current, dict) else None

        from app.models import Notification
        n = Notification.query.get(notification_id)
        if not n:
            return jsonify({'success': False, 'error': 'not found'}), 404
        if n.user_id != uid and role != 'admin':
            return jsonify({'success': False, 'error': 'unauthorized'}), 403

        user_of_notification = n.user_id
        db.session.delete(n)
        db.session.commit()
        # regenerate notifications json for the user
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
        for c in courses:
            # Count lessons
            lessons_count = Lesson.query.filter_by(course_id=c.id).count()
            
            # Get enrollment count (if model exists)
            enrolled_count = 0
            Enrollment = get_enrollment_model()
            if Enrollment:
                try:
                    enrolled_count = Enrollment.query.filter_by(course_id=c.id).count()
                except Exception:
                    pass
            
            courses_list.append({
                'id': c.id,
                'title': c.title,
                'description': c.description or '',
                'category': c.category,
                'thumbnail_url': c.thumbnail_url,
                'level': c.difficulty or 'beginner',
                'duration': c.duration_weeks,
                'weekly_hours': c.weekly_hours,
                'total_lessons': lessons_count,
                'enrolled_count': enrolled_count,
                'rating': 4.5,  # Placeholder - implement rating system
                'featured': c.featured if hasattr(c, 'featured') else False,
                'tags': c.tags if hasattr(c, 'tags') else None
            })
        
        return jsonify({
            'success': True,
            'total': total,
            'courses': courses_list,
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
        
        for l in lessons:
            topics_count = Topic.query.filter_by(lesson_id=l.id).count()
            lessons_list.append({
                'id': l.id,
                'title': l.title,
                'description': l.description or '',
                'duration': l.duration,
                'level': l.level,
                'topics_count': topics_count,
                'objectives': l.objectives
            })
        
        return jsonify({
            'success': True,
            'course': {
                'id': course.id,
                'title': course.title,
                'description': course.description,
                'category': course.category,
                'thumbnail_url': course.thumbnail_url,
                'level': course.difficulty or 'beginner',
                'duration': course.duration_weeks,
                'weekly_hours': course.weekly_hours,
                'total_lessons': len(lessons_list),
                'lessons': lessons_list,
                'tags': course.tags if hasattr(course, 'tags') else None
            }
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
        for c in courses:
            lessons_count = Lesson.query.filter_by(course_id=c.id).count()
            courses_list.append({
                'id': c.id,
                'title': c.title,
                'description': c.description or '',
                'category': c.category,
                'thumbnail_url': c.thumbnail_url,
                'level': c.difficulty or 'beginner',
                'duration': c.duration_weeks,
                'total_lessons': lessons_count
            })
        
        return jsonify({
            'success': True,
            'total': total,
            'category': category_name,
            'courses': courses_list
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
        
        for l in lessons:
            topics_count = Topic.query.filter_by(lesson_id=l.id).count()
            lessons_list.append({
                'id': l.id,
                'title': l.title,
                'description': l.description or '',
                'duration': l.duration,
                'level': l.level,
                'topics_count': topics_count,
                'objectives': l.objectives
            })
        
        return jsonify({
            'success': True,
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
        
        topics_count = Topic.query.filter_by(lesson_id=lesson_id).count()
        
        return jsonify({
            'success': True,
            'lesson': {
                'id': lesson.id,
                'course_id': lesson.course_id,
                'title': lesson.title,
                'description': lesson.description,
                'duration': lesson.duration,
                'level': lesson.level,
                'topics_count': topics_count,
                'objectives': lesson.objectives
            }
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Get lesson detail failed')
        return jsonify({
            'success': False,
            'error': 'Failed to load lesson'
        }), 500


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
            data = t.data_json if isinstance(t.data_json, dict) else {}
            
            topics_list.append({
                'id': t.id,
                'lesson_id': t.lesson_id,
                'title': t.title,
                'content_type': data.get('type', 'text'),
                'content': data.get('content', ''),
                'description': data.get('description', ''),
                'duration': data.get('duration', 2),
                'order': data.get('order', 0),
                'estimated_time': data.get('estimated_time'),
                'difficulty': data.get('difficulty')
            })
        
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
        
        data = topic.data_json if isinstance(topic.data_json, dict) else {}
        
        return jsonify({
            'success': True,
            'topic': {
                'id': topic.id,
                'lesson_id': topic.lesson_id,
                'title': topic.title,
                'content_type': data.get('type', 'text'),
                'content': data.get('content', ''),
                'description': data.get('description', ''),
                'duration': data.get('duration', 2),
                'order': data.get('order', 0),
                'estimated_time': data.get('estimated_time'),
                'difficulty': data.get('difficulty')
            }
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
    return get_topic_detail(topic_id)


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
