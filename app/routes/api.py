# app/routes/api.py

"""
Mobile/Student API endpoints for EduSaint Flutter App
Base URL: https://byte.edusaint.in/api/v1
"""

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity
)
from app.extensions import db
from app.models import User, Course, Lesson, Topic
from sqlalchemy import or_
from datetime import datetime
import traceback

# Create blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api/v1')


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
        name = data.get('name')
        role = data.get('role', 'student')
        
        # Validation
        if not email or not password or not name:
            return jsonify({
                'success': False,
                'error': 'Email, password and name are required'
            }), 400
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({
                'success': False,
                'error': 'Email already registered'
            }), 400
        
        # Create user
        user = User(email=email.strip(), role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        user_id = user.id
        
        # Create profile
        Profile = get_profile_model()
        if Profile:
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
        
        return jsonify({
            'success': True,
            'message': 'User registered successfully',
            'user_id': user_id
        }), 201
        
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
        
        # Find user
        user = User.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            return jsonify({
                'success': False,
                'error': 'Invalid credentials'
            }), 401
        
        # Get profile name
        name = email  # fallback
        Profile = get_profile_model()
        if Profile:
            try:
                profile = Profile.query.filter_by(user_id=user.id).first()
                if profile:
                    name = profile.name
            except Exception:
                pass
        
        # Create JWT tokens
        identity = {
            'user_id': user.id,
            'email': user.email,
            'role': user.role
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
                'role': user.role
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
# PROFILE APIs
# ============================================================================

@api_bp.route('/profile/<int:user_id>', methods=['GET'])
@jwt_required()
def get_profile(user_id):
    """
    Get user profile
    
    Headers:
    Authorization: Bearer <access_token>
    
    Response:
    {
        "success": true,
        "profile": {
            "id": 456,
            "user_id": 123,
            "name": "Student Name",
            "email": "student@test.com",
            "phone": "+91-9876543210",
            "bio": "Learning enthusiast",
            "avatar_url": "https://...",
            "date_of_birth": "2005-06-15",
            "grade": "10th",
            "school": "ABC School"
        }
    }
    """
    try:
        current_user = get_jwt_identity()
        
        # Authorization check
        if current_user['user_id'] != user_id and current_user['role'] != 'admin':
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403
        
        Profile = get_profile_model()
        if not Profile:
            return jsonify({
                'success': False,
                'error': 'Profile feature not available'
            }), 500
        
        profile = Profile.query.filter_by(user_id=user_id).first()
        
        if not profile:
            return jsonify({
                'success': False,
                'error': 'Profile not found'
            }), 404
        
        return jsonify({
            'success': True,
            'profile': {
                'id': profile.id,
                'user_id': profile.user_id,
                'name': profile.name,
                'email': profile.email,
                'phone': profile.phone,
                'bio': profile.bio,
                'avatar_url': profile.avatar_url,
                'date_of_birth': profile.date_of_birth,
                'grade': profile.grade,
                'school': profile.school,
                'created_at': profile.created_at.isoformat() if profile.created_at else None,
                'updated_at': profile.updated_at.isoformat() if profile.updated_at else None
            }
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Get profile failed')
        return jsonify({
            'success': False,
            'error': 'Failed to load profile'
        }), 500


@api_bp.route('/profile', methods=['POST'])
@jwt_required()
def create_profile():
    """
    Create new profile
    
    Request Body:
    {
        "user_id": 123,
        "name": "Student Name",
        "phone": "+91-9876543210",
        "bio": "Learning enthusiast",
        "date_of_birth": "2005-06-15",
        "grade": "10th",
        "school": "ABC School"
    }
    
    Response:
    {
        "success": true,
        "message": "Profile created",
        "profile_id": 456
    }
    """
    try:
        current_user = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        user_id = data.get('user_id')
        
        # Authorization check
        if current_user['user_id'] != user_id:
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403
        
        Profile = get_profile_model()
        if not Profile:
            return jsonify({
                'success': False,
                'error': 'Profile feature not available'
            }), 500
        
        # Check if profile already exists
        existing = Profile.query.filter_by(user_id=user_id).first()
        if existing:
            return jsonify({
                'success': False,
                'error': 'Profile already exists'
            }), 400
        
        # Create profile
        profile = Profile(
            user_id=user_id,
            name=data.get('name', ''),
            email=current_user.get('email', ''),
            phone=data.get('phone'),
            bio=data.get('bio'),
            date_of_birth=data.get('date_of_birth'),
            grade=data.get('grade'),
            school=data.get('school')
        )
        
        db.session.add(profile)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Profile created',
            'profile_id': profile.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Create profile failed')
        return jsonify({
            'success': False,
            'error': 'Failed to create profile'
        }), 500


@api_bp.route('/profile/<int:user_id>', methods=['PUT'])
@jwt_required()
def update_profile(user_id):
    """
    Update profile
    
    Request Body (all fields optional):
    {
        "name": "Updated Name",
        "phone": "+91-9876543210",
        "bio": "Updated bio",
        "date_of_birth": "2005-06-15",
        "grade": "11th",
        "school": "XYZ School"
    }
    
    Response:
    {
        "success": true,
        "message": "Profile updated"
    }
    """
    try:
        current_user = get_jwt_identity()
        
        # Authorization check
        if current_user['user_id'] != user_id:
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403
        
        Profile = get_profile_model()
        if not Profile:
            return jsonify({
                'success': False,
                'error': 'Profile feature not available'
            }), 500
        
        profile = Profile.query.filter_by(user_id=user_id).first()
        
        if not profile:
            return jsonify({
                'success': False,
                'error': 'Profile not found'
            }), 404
        
        data = request.get_json()
        
        # Update fields if provided
        if 'name' in data:
            profile.name = data['name']
        if 'phone' in data:
            profile.phone = data['phone']
        if 'bio' in data:
            profile.bio = data['bio']
        if 'date_of_birth' in data:
            profile.date_of_birth = data['date_of_birth']
        if 'grade' in data:
            profile.grade = data['grade']
        if 'school' in data:
            profile.school = data['school']
        if 'avatar_url' in data:
            profile.avatar_url = data['avatar_url']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Profile updated'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Update profile failed')
        return jsonify({
            'success': False,
            'error': 'Failed to update profile'
        }), 500


@api_bp.route('/profile/<int:user_id>', methods=['DELETE'])
@jwt_required()
def delete_profile(user_id):
    """
    Delete profile
    
    Response:
    {
        "success": true,
        "message": "Profile deleted"
    }
    """
    try:
        current_user = get_jwt_identity()
        
        # Authorization check
        if current_user['user_id'] != user_id and current_user['role'] != 'admin':
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403
        
        Profile = get_profile_model()
        if not Profile:
            return jsonify({
                'success': False,
                'error': 'Profile feature not available'
            }), 500
        
        profile = Profile.query.filter_by(user_id=user_id).first()
        
        if not profile:
            return jsonify({
                'success': False,
                'error': 'Profile not found'
            }), 404
        
        db.session.delete(profile)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Profile deleted'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Delete profile failed')
        return jsonify({
            'success': False,
            'error': 'Failed to delete profile'
        }), 500


@api_bp.route('/profile/avatar', methods=['POST'])
@jwt_required()
def upload_avatar():
    """
    Upload profile avatar (multipart/form-data)
    
    Form Data:
    - user_id: 123
    - avatar: [file]
    
    Response:
    {
        "success": true,
        "avatar_url": "https://byte.edusaint.in/media/avatars/123.jpg"
    }
    """
    try:
        from werkzeug.utils import secure_filename
        import os
        import uuid
        
        current_user = get_jwt_identity()
        user_id = int(request.form.get('user_id'))
        
        # Authorization check
        if current_user['user_id'] != user_id:
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403
        
        if 'avatar' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file provided'
            }), 400
        
        file = request.files['avatar']
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400
        
        # Validate file type
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
        if not ('.' in file.filename and
                file.filename.rsplit('.', 1)[1].lower() in allowed_extensions):
            return jsonify({
                'success': False,
                'error': 'Invalid file type. Allowed: png, jpg, jpeg, gif'
            }), 400
        
        # Generate unique filename
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{user_id}_{uuid.uuid4().hex}.{ext}"
        
        # Save file
        upload_path = current_app.config.get('UPLOAD_PATH', '/tmp/uploads')
        if not os.path.isabs(upload_path):
            upload_path = os.path.join(current_app.root_path, upload_path)
        
        avatars_dir = os.path.join(upload_path, 'avatars')
        os.makedirs(avatars_dir, exist_ok=True)
        
        file_path = os.path.join(avatars_dir, filename)
        file.save(file_path)
        
        # Generate URL
        avatar_url = f"/uploads/avatars/{filename}"
        
        # Update profile
        Profile = get_profile_model()
        if Profile:
            profile = Profile.query.filter_by(user_id=user_id).first()
            if profile:
                profile.avatar_url = avatar_url
                db.session.commit()
        
        return jsonify({
            'success': True,
            'avatar_url': avatar_url
        }), 200
        
    except Exception as e:
        current_app.logger.exception('Avatar upload failed')
        return jsonify({
            'success': False,
            'error': 'Failed to upload avatar'
        }), 500


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

@api_bp.route('/student/enrollments', methods=['GET'])
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
        current_user = get_jwt_identity()
        student_id = current_user['user_id']
        
        Enrollment = get_enrollment_model()
        
        if not Enrollment:
            # Return empty list if enrollment model doesn't exist yet
            return jsonify({
                'success': True,
                'enrollments': [],
                'message': 'Enrollment feature not yet available'
            }), 200
        
        enrollments = Enrollment.query.filter_by(
            student_id=student_id,
            is_active=True
        ).all()
        
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
                        progress = Progress.query.filter_by(
                            student_id=student_id,
                            topic_id=topic.id,
                            completed=True
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
                'enrolled_at': e.enrolled_at.isoformat() if e.enrolled_at else None,
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
        current_user = get_jwt_identity()
        student_id = current_user['user_id']
        
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
        existing = Enrollment.query.filter_by(
            student_id=student_id,
            course_id=course_id
        ).first()
        
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
            student_id=student_id,
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
        current_user = get_jwt_identity()
        student_id = current_user['user_id']
        
        Enrollment = get_enrollment_model()
        
        if not Enrollment:
            return jsonify({
                'success': False,
                'error': 'Enrollment feature not yet available'
            }), 501
        
        enrollment = Enrollment.query.filter_by(
            student_id=student_id,
            course_id=course_id
        ).first()
        
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
        current_user = get_jwt_identity()
        student_id = current_user['user_id']
        
        Enrollment = get_enrollment_model()
        
        if not Enrollment:
            return jsonify({
                'success': True,
                'enrolled': False,
                'message': 'Enrollment feature not yet available'
            }), 200
        
        enrollment = Enrollment.query.filter_by(
            student_id=student_id,
            course_id=course_id,
            is_active=True
        ).first()
        
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

@api_bp.route('/student/progress', methods=['GET'])
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
        current_user = get_jwt_identity()
        student_id = current_user['user_id']
        
        Enrollment = get_enrollment_model()
        Progress = get_progress_model()
        
        # Calculate stats
        total_enrolled = 0
        total_completed = 0
        total_topics_completed = 0
        total_learning_time = 0
        
        if Enrollment:
            total_enrolled = Enrollment.query.filter_by(
                student_id=student_id,
                is_active=True
            ).count()
            
            total_completed = Enrollment.query.filter_by(
                student_id=student_id,
                is_active=True
            ).filter(Enrollment.completed_at.isnot(None)).count()
        
        if Progress:
            completed_progress = Progress.query.filter_by(
                student_id=student_id,
                completed=True
            ).all()
            
            total_topics_completed = len(completed_progress)
            total_learning_time = sum(p.time_spent or 0 for p in completed_progress)
        
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


@api_bp.route('/student/progress/<int:course_id>', methods=['GET'])
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
        current_user = get_jwt_identity()
        student_id = current_user['user_id']
        
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
                    progress = Progress.query.filter_by(
                        student_id=student_id,
                        topic_id=topic.id
                    ).first()
                    
                    if progress:
                        if progress.completed:
                            completed_topics += 1
                        time_spent += progress.time_spent or 0
        
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
        current_user = get_jwt_identity()
        student_id = current_user['user_id']
        
        data = request.get_json()
        
        topic_id = data.get('topic_id')
        time_spent = data.get('time_spent', 0)
        completed = data.get('completed', False)
        
        if not topic_id:
            return jsonify({
                'success': False,
                'error': 'Topic ID required'
            }), 400
        
        # Check if topic exists
        topic = Topic.query.get(topic_id)
        if not topic:
            return jsonify({
                'success': False,
                'error': 'Topic not found'
            }), 404
        
        Progress = get_progress_model()
        
        if not Progress:
            return jsonify({
                'success': False,
                'error': 'Progress tracking not yet available'
            }), 501
        
        # Check if progress record exists
        progress = Progress.query.filter_by(
            student_id=student_id,
            topic_id=topic_id
        ).first()
        
        if progress:
            # Update existing
            if time_spent:
                progress.time_spent = (progress.time_spent or 0) + time_spent
            if completed:
                progress.completed = True
            progress.updated_at = datetime.utcnow()
        else:
            # Create new
            progress = Progress(
                student_id=student_id,
                topic_id=topic_id,
                time_spent=time_spent,
                completed=completed,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.session.add(progress)
        
        db.session.commit()
        
        # Calculate course progress
        lesson = Lesson.query.get(topic.lesson_id)
        course_progress = 0
        
        if lesson:
            lessons = Lesson.query.filter_by(course_id=lesson.course_id).all()
            total_topics = 0
            completed_topics = 0
            
            for l in lessons:
                topics = Topic.query.filter_by(lesson_id=l.id).all()
                total_topics += len(topics)
                
                for t in topics:
                    p = Progress.query.filter_by(
                        student_id=student_id,
                        topic_id=t.id,
                        completed=True
                    ).first()
                    if p:
                        completed_topics += 1
            
            if total_topics > 0:
                course_progress = round((completed_topics / total_topics) * 100, 2)
        
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


@api_bp.route('/progress/complete-topic', methods=['POST'])
@jwt_required()
def complete_topic():
    """
    Mark topic as complete
    
    Request Body:
    {
        "topic_id": 502
    }
    
    Response:
    {
        "success": true,
        "message": "Topic marked as complete"
    }
    """
    data = request.get_json()
    data['completed'] = True
    
    # Reuse update_progress function
    return update_progress()


@api_bp.route('/student/stats', methods=['GET'])
@jwt_required()
def get_student_stats():
    """
    Get learning statistics (alias for overall progress)
    """
    return get_overall_progress()


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
