from flask import request, current_app, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from werkzeug.utils import secure_filename
from ..models import Progress, User, Leaderboard, Student, Staff
from ..extensions import db, limiter
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from . import bp
from ..utils.dynamic_json import generate_user_progress_json, generate_students_json
import os
from pathlib import Path


def _get_current_student():
    """Resolve the logged-in student's record using JWT identity (matches on email).

    Returns (student, error_response) where error_response is a Flask response when
    resolution fails.
    """
    claims = get_jwt()
    if not claims:
        return None, ({"success": False, "error": "Not authenticated", "code": 401}, 401)

    email = claims.get('email')
    if not email:
        return None, ({"success": False, "error": "No email associated with token", "code": 400}, 400)

    student = Student.query.filter_by(email=email).first()
    if not student:
        return None, ({"success": False, "error": "Student record not found", "code": 404}, 404)

    return student, None


def update_leaderboard():
    """Recalculate and update leaderboard rankings based on scores.
    
    Ranks students by score (descending), then alphabetically by name.
    Only includes students who have attempted quizzes (score > 0).
    """
    try:
        from datetime import datetime
        
        # Calculate total score per student - only include students with progress entries
        student_scores = db.session.query(
            Student.id,
            Student.name,
            func.sum(Progress.score).label('total_score')
        ).join(
            Progress, Student.id == Progress.user_id
        ).group_by(
            Student.id, Student.name
        ).having(
            func.sum(Progress.score) > 0
        ).order_by(
            func.sum(Progress.score).desc(),
            Student.name.asc()
        ).all()
        
        # Clear and rebuild leaderboard
        Leaderboard.query.delete()
        
        for rank, (student_id, name, score) in enumerate(student_scores, start=1):
            league = 'platinum' if score >= 900 else 'gold' if score >= 700 else 'silver' if score >= 400 else 'bronze'
            entry = Leaderboard(
                rank=rank,
                name=name or 'Unknown',
                score=float(score or 0),
                last_updated_date=datetime.utcnow(),
                league=league
            )
            db.session.add(entry)
        
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to update leaderboard')


@bp.route("/progress", methods=["POST"])
@limiter.limit("30/minute")
def submit_progress():
    """Accept a progress submission. Prevent duplicate submissions when attempt_id is provided.

    Expected JSON: { user_id, lesson_id, score?, time_spent?, answers?, attempt_id? }
    """
    data = request.get_json(silent=True)
    if not data:
        return {"success": False, "error": "JSON payload required", "code": 400}, 400

    # Basic validation and type coercion
    try:
        user_id = int(data.get("user_id")) if data.get("user_id") is not None else None
    except Exception:
        return {"success": False, "error": "user_id must be integer", "code": 400}, 400
    try:
        lesson_id = int(data.get("lesson_id")) if data.get("lesson_id") is not None else None
    except Exception:
        return {"success": False, "error": "lesson_id must be integer", "code": 400}, 400

    if not (user_id and lesson_id):
        return {"success": False, "error": "user_id and lesson_id required", "code": 400}, 400

    attempt_id = data.get("attempt_id")
    score = data.get("score")
    time_spent = data.get("time_spent")
    answers = data.get("answers")

    # Prevent duplicate submission when attempt_id is provided
    if attempt_id:
        exists = Progress.query.filter_by(attempt_id=attempt_id, user_id=user_id, lesson_id=lesson_id).first()
        if exists:
            current_app.logger.info('Duplicate progress submission attempt_id=%s user_id=%s lesson_id=%s', attempt_id, user_id, lesson_id)
            return {"success": False, "error": "duplicate submission", "code": 409}, 409

    # Insert within a transaction
    p = Progress(user_id=user_id, lesson_id=lesson_id, score=score, time_spent=time_spent, answers=answers, attempt_id=attempt_id)
    try:
        with db.session.begin():
            db.session.add(p)
        # Best-effort: regenerate the user's progress JSON for cloud sync
        try:
            generate_user_progress_json(user_id)
        except Exception:
            current_app.logger.exception('Failed to regen user progress json after submit_progress')
        
        # Update leaderboard after progress submission
        try:
            update_leaderboard()
        except Exception:
            current_app.logger.exception('Failed to update leaderboard after progress submission')
        
        return {"success": True, "id": p.id}
    except IntegrityError as e:
        # likely FK or constraint violation
        current_app.logger.exception('Progress insert IntegrityError')
        return {"success": False, "error": "db integrity error", "detail": str(e), "code": 500}, 500
    except Exception as e:
        current_app.logger.exception('Progress insert failed')
        return {"success": False, "error": "db error", "detail": str(e), "code": 500}, 500


@bp.route("/leaderboard", methods=["GET"])
@limiter.limit("60/minute")
def get_leaderboard():
    """Fetch leaderboard data directly from leaderboard table.
    
    Query parameters:
    - limit: Number of top students to return (default: 50, max: 100)
    
    Returns:
    {
        "leaderboard": [
            {
                "rank": 1,
                "user_id": 123,
                "name": "User Name",
                "score": 950.5,
                "status": "active"
            },
            ...
        ]
    }
    """
    try:
        limit = int(request.args.get('limit', 50))
        limit = min(limit, 100)  # Cap at 100
        limit = max(limit, 1)    # Minimum 1
    except (ValueError, TypeError):
        limit = 50
    
    # Fetch from leaderboard table ordered by rank
    leaderboard_rows = Leaderboard.query.order_by(
        Leaderboard.rank.asc()
    ).limit(limit).all()
    
    # Build response
    leaderboard = []
    for entry in leaderboard_rows:
        last_updated = ""
        if entry.last_updated_date:
            try:
                last_updated = entry.last_updated_date.strftime('%Y-%m-%d')
            except Exception:
                last_updated = ""

        # Status column not present in DB; default to 'active'
        status_val = getattr(entry, 'status', None) or 'active'

        leaderboard.append({
            "rank": entry.rank,
            "name": entry.name,
            "score": entry.score,
            "status": status_val,
            "last_updated_date": last_updated,
            "league": getattr(entry, 'league', None)
        })
    
    # Include success flag for clients that expect it
    return {"success": True, "leaderboard": leaderboard}, 200


@bp.route("/students", methods=["GET"])
@limiter.limit("60/minute")
def get_students():
    """Fetch students data from the students table.
    
    Query parameters:
    - limit: Number of students to return (default: 50, max: 100)
    - page: Page number for pagination (default: 1)
    - search: Search by name or email
    
    Returns:
    {
        "students": [
            {
                "id": 1,
                "name": "Student Name",
                "email": "student@example.com",
                "enrollmentDate": "2023-01-15",
                "courses": 0,
                "progress": 0,
                "xp": 0,
                "lastLogin": "",
                "status": "active"
            },
            ...
        ],
        "total": 150
    }
    """
    try:
        limit = int(request.args.get('limit', 50))
        limit = min(limit, 100)
        limit = max(limit, 1)
        page = int(request.args.get('page', 1))
        page = max(page, 1)
    except (ValueError, TypeError):
        limit, page = 50, 1
    
    search = request.args.get('search', '').lower()
    
    # Base query
    query = Student.query
    
    # Apply filters
    if search:
        query = query.filter(
            (Student.name.ilike(f'%{search}%')) |
            (Student.email.ilike(f'%{search}%'))
        )
    
    # Get total count before pagination
    total = query.count()
    
    # Paginate and order by ID ascending
    offset = (page - 1) * limit
    students_list = query.order_by(Student.id.asc()).offset(offset).limit(limit).all()
    
    # Build response
    students = []
    for student in students_list:
        # Format enrollment date
        enrollment_date = ""
        if student.date:
            try:
                enrollment_date = student.date.strftime('%Y-%m-%d')
            except:
                enrollment_date = ""
        
        students.append({
            "id": student.id,
            "name": student.name or "Unknown",
            "email": student.email or "",
            "enrollmentDate": enrollment_date,
            # Map Courses column using courses field, fallback to legacy subjects
            "courses": (getattr(student, 'courses', None) or getattr(student, 'subjects', None) or ""),
            "syllabus": getattr(student, 'syllabus', None),
            "class": getattr(student, 'class_', None),
            "progress": 0,
            "xp": 0,
            "lastLogin": "",
            "status": getattr(student, 'status', 'active'),
            "image": getattr(student, 'image', None),
            "mobile": getattr(student, 'mobile', None)
        })
    
    return {
        "students": students,
        "total": total,
        "page": page,
        "limit": limit
    }, 200


@bp.route("/students/<int:student_id>", methods=["GET"])
@limiter.limit("60/minute")
def get_student(student_id):
    """Fetch a single student by ID.
    
    Returns:
    {
        "id": 1,
        "name": "Student Name",
        "email": "student@example.com",
        "enrollmentDate": "2023-01-15",
        "courses": "Math,Science",
        "progress": 0,
        "xp": 0,
        "lastLogin": "",
        "status": "active"
    }
                send_email = bool(data.get('sendEmail', False))
                send_sms = bool(data.get('sendSms', False))
                notifications = {
                    'email': {'requested': bool(send_email), 'sent': False},
                    'sms': {'requested': bool(send_sms), 'sent': False},
                }
    """
    student = Student.query.get(student_id)
    if not student:
        return {"success": False, "error": "Student not found", "code": 404}, 404
    
    # Format enrollment date
    enrollment_date = ""
    if student.date:
        try:
            enrollment_date = student.date.strftime('%Y-%m-%d')
        except:
            enrollment_date = ""
    
    return {
        "id": student.id,
        "name": student.name or "Unknown",
        "email": student.email or "",
        "enrollmentDate": enrollment_date,
        "courses": (getattr(student, 'courses', None) or getattr(student, 'subjects', None) or ""),
        "syllabus": getattr(student, 'syllabus', None),
        "class": getattr(student, 'class_', None),
        "progress": 0,
        "xp": 0,
        "lastLogin": "",
        "status": getattr(student, 'status', 'active'),
        "image": getattr(student, 'image', None),
        "mobile": getattr(student, 'mobile', None)
    }, 200


@bp.route("/students", methods=["POST"])
@jwt_required()
@limiter.limit("30/minute")
def create_student():
    """Create a new student record in the database. Admin only.

    Expected JSON (all fields besides name/email optional):

    {
        "name": "Full Name",          # required
        "email": "student@example.com",  # required
        "courses": "...",            # optional, or legacy "subjects"
        "date": "YYYY-MM-DD",        # optional enrollment date
        "mobile": "9876543210",      # optional 10-digit mobile
        "class": "10",               # optional class/grade
        "syllabus": "CBSE",          # optional board/syllabus
        "password": "...",           # optional raw password (stored in students table only)
        "status": "active"|"inactive",  # optional status, defaults to "active"
        "sendEmail": true|false,     # optional, default true
        "sendSms": true|false,       # optional, default false (not implemented)
        "second_language": "...",    # optional
        "third_language": "..."      # optional
    }

    Accepts legacy "subjects" instead of "courses".
    """
    # Check if user is admin
    claims = get_jwt()
    if not claims or claims.get('role') != 'admin':
        return {"success": False, "error": "Admin access required", "code": 403}, 403
    
    data = request.get_json(silent=True)
    if not data:
        return {"success": False, "error": "JSON payload required", "code": 400}, 400
    
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    
    if not name or not email:
        return {"success": False, "error": "Name and email are required", "code": 400}, 400
    
    try:
        send_email = bool(data.get('sendEmail', True))
        send_sms = bool(data.get('sendSms', False))

        # Reject duplicate email if it is already used by any student, staff or user.
        # This keeps emails globally unique across all account types.
        existing_student = Student.query.filter(Student.email.ilike(email)).first()
        existing_staff = Staff.query.filter(Staff.email.ilike(email)).first()
        existing_user = User.query.filter(User.email.ilike(email)).first()
        if existing_student or existing_staff or existing_user:
            return {"success": False, "error": "email already exists", "code": 400}, 400

        # Optional mobile validation (10 digits)
        mobile_in = data.get('mobile')
        mobile_val = None
        if mobile_in:
            m = str(mobile_in)
            if len(m) == 10 and m.isdigit():
                mobile_val = m
            else:
                return {"success": False, "error": "Mobile must be 10 digits", "code": 400}, 400

        # Status (active/inactive), default active
        status_val = 'active'
        if 'status' in data and data['status'] in ['active', 'inactive']:
            status_val = data['status']

        # Prefer courses; fallback to legacy subjects
        courses_val = data.get('courses', data.get('subjects', ''))

        new_student = Student(
            name=name,
            email=email,
            courses=courses_val,
            # Store raw password in Student table (legacy behavior, similar to /auth/register)
            password=data.get('password', ''),
            syllabus=data.get('syllabus', data.get('board', '')),
            class_=data.get('class', ''),
            second_language=data.get('second_language', ''),
            third_language=data.get('third_language', ''),
            mobile=mobile_val,
            status=status_val
        )

        # Also create/update a User record so /api/v1/auth/login works (hashed password).
        # Only do this when a non-empty password is provided.
        pw_in = data.get('password')
        if pw_in is not None and str(pw_in).strip() != '':
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                # Keep role as-is; just update password
                existing_user.set_password(str(pw_in))
            else:
                u = User(email=email, role='student')
                u.set_password(str(pw_in))
                db.session.add(u)
        
        # Parse enrollment date if provided
        date_str = data.get('date', '').strip()
        if date_str:
            from datetime import datetime
            try:
                new_student.date = datetime.strptime(date_str, '%Y-%m-%d')
            except:
                pass
        
        db.session.add(new_student)
        db.session.commit()

        notifications = {
            'email': {'requested': bool(send_email), 'sent': False},
            'sms': {'requested': bool(send_sms), 'sent': False},
        }

        # Send credentials email (best-effort). Only possible when password is provided.
        if send_email:
            pw_in = data.get('password')
            if pw_in is not None and str(pw_in).strip() != '':
                try:
                    from app.utils.emailer import send_student_credentials_email

                    login_url = (current_app.config.get('APP_PUBLIC_LOGIN_URL') or '').strip()
                    if not login_url:
                        # Fallback to backend origin; replace with your frontend login URL via APP_PUBLIC_LOGIN_URL
                        login_url = (request.host_url or '').rstrip('/')[0:]

                    ok, err = send_student_credentials_email(
                        to_email=email,
                        student_name=name,
                        password=str(pw_in),
                        login_url=login_url,
                    )
                    notifications['email']['sent'] = bool(ok)
                    if err:
                        notifications['email']['error'] = err
                except Exception as e:
                    current_app.logger.exception('Failed to send credentials email')
                    notifications['email']['sent'] = False
                    notifications['email']['error'] = str(e)
            else:
                notifications['email']['sent'] = False
                notifications['email']['error'] = 'Password missing; cannot send credentials'

        # SMS sending is not implemented in this backend yet.
        if send_sms:
            notifications['sms']['sent'] = False
            notifications['sms']['error'] = 'SMS delivery not implemented'

        # Regenerate students JSON
        try:
            generate_students_json()
        except Exception:
            current_app.logger.exception('Failed to regenerate students.json after create')
        return {"success": True, "id": new_student.id, "notifications": notifications}, 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to create student')
        return {"success": False, "error": "Create failed", "detail": str(e), "code": 500}, 500


@bp.route("/me/student", methods=["PUT"])
@jwt_required()
def update_current_student():
    """Allow a logged-in student to update their own profile.

    Expected JSON: { name?, email?, mobile?, class?, courses? } (accepts legacy subjects)
    """
    data = request.get_json(silent=True)
    if not data:
        return {"success": False, "error": "JSON payload required", "code": 400}, 400

    student, error = _get_current_student()
    if error:
        return error

    try:
        if 'name' in data:
            student.name = data['name']
        if 'email' in data:
            # update email in student record
            student.email = data['email']
        if 'mobile' in data:
            mobile = data['mobile']
            if mobile and len(mobile) == 10 and str(mobile).isdigit():
                student.mobile = str(mobile)
            elif not mobile:
                student.mobile = None
            else:
                return {"success": False, "error": "Mobile must be 10 digits", "code": 400}, 400
        if 'class' in data:
            student.class_ = data['class']
        # Prefer courses; fallback to legacy subjects
        if 'courses' in data:
            student.courses = data['courses']
        elif 'subjects' in data:
            student.courses = data['subjects']

        db.session.commit()
        try:
            generate_students_json()
        except Exception:
            current_app.logger.exception('Failed to regenerate students.json after /me/student update')

        return {"success": True, "id": student.id}, 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to update current student')
        return {"success": False, "error": "Update failed", "detail": str(e), "code": 500}, 500


@bp.route("/me/student/avatar", methods=["POST"])
@jwt_required()
def upload_current_student_avatar():
    """Upload avatar for the logged-in student (multipart/form-data with 'avatar')."""
    student, error = _get_current_student()
    if error:
        return error

    if 'avatar' not in request.files:
        return {"success": False, "error": "No avatar file provided", "code": 400}, 400

    file = request.files['avatar']
    if file.filename == '':
        return {"success": False, "error": "No file selected", "code": 400}, 400

    allowed_extensions = {'jpg', 'jpeg', 'png', 'gif'}
    filename = secure_filename(file.filename)
    file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if file_ext not in allowed_extensions:
        return {"success": False, "error": f"Invalid file type. Allowed: {', '.join(allowed_extensions)}", "code": 400}, 400

    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > 5 * 1024 * 1024:
        return {"success": False, "error": "File too large. Maximum size: 5MB", "code": 400}, 400

    try:
        upload_base = current_app.config.get('UPLOAD_PATH', 'uploads')
        if not Path(upload_base).is_absolute():
            project_root = Path(current_app.root_path).parent
            upload_base = project_root / upload_base
        avatars_dir = Path(upload_base) / 'avatars'
        avatars_dir.mkdir(parents=True, exist_ok=True)

        new_filename = f"student_{student.id}_avatar.{file_ext}"
        file_path = avatars_dir / new_filename

        if student.image:
            old_file_path = Path(upload_base) / student.image.lstrip('/')
            if old_file_path.exists():
                try:
                    old_file_path.unlink()
                except Exception:
                    current_app.logger.warning(f'Failed to delete old avatar: {old_file_path}')

        file.save(str(file_path))

        relative_path = f"/avatars/{new_filename}"
        student.image = relative_path
        db.session.commit()

        try:
            generate_students_json()
        except Exception:
            current_app.logger.exception('Failed to regenerate students.json after /me/student/avatar upload')

        return {"success": True, "image_path": relative_path}, 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to upload current student avatar')
        return {"success": False, "error": "Upload failed", "detail": str(e), "code": 500}, 500
@bp.route("/students/<int:student_id>", methods=["PUT"])
@jwt_required()
@limiter.limit("30/minute")
def update_student(student_id):
    """Update a student record in the database. Admin only.
    
    Expected JSON: { name?, email?, courses?, date?, status?, mobile?, class?, syllabus?, password? } (accepts legacy subjects/board)
    """
    # Check if user is admin
    claims = get_jwt()
    if not claims or claims.get('role') != 'admin':
        return {"success": False, "error": "Admin access required", "code": 403}, 403
    
    data = request.get_json(silent=True)
    if not data:
        return {"success": False, "error": "JSON payload required", "code": 400}, 400
    
    student = Student.query.get(student_id)
    if not student:
        return {"success": False, "error": "Student not found", "code": 404}, 404
    
    try:
        original_email = (student.email or '').strip().lower()

        send_email = bool(data.get('sendEmail', False))
        send_sms = bool(data.get('sendSms', False))
        notifications = {
            'email': {'requested': bool(send_email), 'sent': False},
            'sms': {'requested': bool(send_sms), 'sent': False},
        }

        # Update fields if provided
        if 'name' in data:
            student.name = data['name']
        if 'email' in data:
            new_email_val = (data['email'] or '').strip().lower()
            if new_email_val and new_email_val != original_email:
                # Ensure the new email is not used by any other student/staff/user
                existing_student = Student.query.filter(Student.email.ilike(new_email_val), Student.id != student.id).first()
                existing_staff = Staff.query.filter(Staff.email.ilike(new_email_val)).first()
                existing_user = User.query.filter(User.email.ilike(new_email_val)).first()
                if existing_student or existing_staff or existing_user:
                    return {"success": False, "error": "email already exists", "code": 400}, 400
                student.email = new_email_val
        # Prefer courses; fallback to legacy subjects
        if 'courses' in data:
            student.courses = data['courses']
        elif 'subjects' in data:
            student.courses = data['subjects']
        if 'date' in data:
            # Parse date string to datetime
            date_str = data['date']
            if date_str:
                from datetime import datetime
                try:
                    student.date = datetime.strptime(date_str, '%Y-%m-%d')
                except:
                    pass
            else:
                student.date = None
        if 'status' in data:
            # Admin can change status (active/inactive)
            if data['status'] in ['active', 'inactive']:
                student.status = data['status']
        if 'mobile' in data:
            mobile = data['mobile']
            if mobile and len(str(mobile)) == 10 and str(mobile).isdigit():
                student.mobile = str(mobile)
            elif not mobile:
                student.mobile = None
        if 'class' in data:
            student.class_ = data['class']

        # Optional password update (admin-driven). Keep behavior consistent with create_student.
        if 'password' in data:
            pw = data['password']
            if pw is None or str(pw).strip() == '':
                # Do not overwrite existing password with empty
                pass
            else:
                student.password = str(pw)

        # Sync to User auth table when password/email are changed so /api/v1/auth/login works.
        if ('password' in data) or ('email' in data):
            new_email = (student.email or '').strip().lower()
            pw = data.get('password') if 'password' in data else None

            # Find user by original email first, then by new email.
            user = None
            if original_email:
                user = User.query.filter_by(email=original_email).first()
            if not user and new_email:
                user = User.query.filter_by(email=new_email).first()

            # Handle email change on User record
            if user and ('email' in data) and new_email and user.email != new_email:
                conflict = User.query.filter(User.email == new_email, User.id != user.id).first()
                if conflict:
                    return {"success": False, "error": "Email already registered", "code": 400}, 400
                user.email = new_email

            # Handle password change on User record
            if pw is not None and str(pw).strip() != '':
                if user:
                    user.set_password(str(pw))
                elif new_email:
                    # Create a user record if missing (needed for JWT-based login)
                    u = User(email=new_email, role='student')
                    u.set_password(str(pw))
                    db.session.add(u)

        # Keep naming consistent with create_student (syllabus) and UI label (board)
        if 'syllabus' in data:
            student.syllabus = data['syllabus']
        elif 'board' in data:
            student.syllabus = data['board']
        
        db.session.commit()

        # Best-effort: send new password via email if requested.
        if send_email and ('password' in data) and (data.get('password') is not None) and str(data.get('password')).strip() != '':
            try:
                from app.utils.emailer import send_student_new_password_email

                login_url = (current_app.config.get('APP_PUBLIC_LOGIN_URL') or '').strip()
                if not login_url:
                    login_url = (request.host_url or '').rstrip('/')

                ok, err = send_student_new_password_email(
                    to_email=(student.email or '').strip(),
                    student_name=(student.name or ''),
                    password=str(data.get('password')),
                    login_url=login_url,
                )
                notifications['email']['sent'] = bool(ok)
                if err:
                    notifications['email']['error'] = err
            except Exception as e:
                current_app.logger.exception('Failed to send new password email')
                notifications['email']['sent'] = False
                notifications['email']['error'] = str(e)

        if send_sms:
            notifications['sms']['sent'] = False
            notifications['sms']['error'] = 'SMS delivery not implemented'

        # Regenerate students JSON
        try:
            generate_students_json()
        except Exception:
            current_app.logger.exception('Failed to regenerate students.json after update')
        return {"success": True, "id": student.id, "notifications": notifications}, 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to update student')
        return {"success": False, "error": "Update failed", "detail": str(e), "code": 500}, 500


@bp.route("/students/<int:student_id>/update", methods=["POST"])
@jwt_required()
@limiter.limit("30/minute")
def update_student_fallback_post(student_id):
    """Fallback update endpoint for environments where PUT is blocked upstream.

    Mirrors the PUT /students/<id> logic with the same admin checks.
    """
    # Admin check
    claims = get_jwt()
    if not claims or claims.get('role') != 'admin':
        return {"success": False, "error": "Admin access required", "code": 403}, 403

    data = request.get_json(silent=True)
    if not data:
        return {"success": False, "error": "JSON payload required", "code": 400}, 400

    student = Student.query.get(student_id)
    if not student:
        return {"success": False, "error": "Student not found", "code": 404}, 404

    try:
        original_email = (student.email or '').strip().lower()

        send_email = bool(data.get('sendEmail', False))
        send_sms = bool(data.get('sendSms', False))
        notifications = {
            'email': {'requested': bool(send_email), 'sent': False},
            'sms': {'requested': bool(send_sms), 'sent': False},
        }
        if 'name' in data:
            student.name = data['name']
        if 'email' in data:
            new_email_val = (data['email'] or '').strip().lower()
            if new_email_val and new_email_val != original_email:
                existing_student = Student.query.filter(Student.email.ilike(new_email_val), Student.id != student.id).first()
                existing_staff = Staff.query.filter(Staff.email.ilike(new_email_val)).first()
                existing_user = User.query.filter(User.email.ilike(new_email_val)).first()
                if existing_student or existing_staff or existing_user:
                    return {"success": False, "error": "email already exists", "code": 400}, 400
                student.email = new_email_val
        if 'courses' in data:
            student.courses = data['courses']
        elif 'subjects' in data:
            student.courses = data['subjects']
        if 'date' in data:
            date_str = data['date']
            if date_str:
                from datetime import datetime
                try:
                    student.date = datetime.strptime(date_str, '%Y-%m-%d')
                except:
                    pass
            else:
                student.date = None
        if 'status' in data:
            if data['status'] in ['active', 'inactive']:
                student.status = data['status']
        if 'mobile' in data:
            mobile = data['mobile']
            if mobile and len(str(mobile)) == 10 and str(mobile).isdigit():
                student.mobile = str(mobile)
            elif not mobile:
                student.mobile = None
        if 'class' in data:
            student.class_ = data['class']

        if 'password' in data:
            pw = data['password']
            if pw is None or str(pw).strip() == '':
                pass
            else:
                student.password = str(pw)

        if ('password' in data) or ('email' in data):
            new_email = (student.email or '').strip().lower()
            pw = data.get('password') if 'password' in data else None

            user = None
            if original_email:
                user = User.query.filter_by(email=original_email).first()
            if not user and new_email:
                user = User.query.filter_by(email=new_email).first()

            if user and ('email' in data) and new_email and user.email != new_email:
                conflict = User.query.filter(User.email == new_email, User.id != user.id).first()
                if conflict:
                    return {"success": False, "error": "Email already registered", "code": 400}, 400
                user.email = new_email

            if pw is not None and str(pw).strip() != '':
                if user:
                    user.set_password(str(pw))
                elif new_email:
                    u = User(email=new_email, role='student')
                    u.set_password(str(pw))
                    db.session.add(u)

        if 'syllabus' in data:
            student.syllabus = data['syllabus']
        elif 'board' in data:
            student.syllabus = data['board']

        db.session.commit()

        if send_email and ('password' in data) and (data.get('password') is not None) and str(data.get('password')).strip() != '':
            try:
                from app.utils.emailer import send_student_new_password_email

                login_url = (current_app.config.get('APP_PUBLIC_LOGIN_URL') or '').strip()
                if not login_url:
                    login_url = (request.host_url or '').rstrip('/')

                ok, err = send_student_new_password_email(
                    to_email=(student.email or '').strip(),
                    student_name=(student.name or ''),
                    password=str(data.get('password')),
                    login_url=login_url,
                )
                notifications['email']['sent'] = bool(ok)
                if err:
                    notifications['email']['error'] = err
            except Exception as e:
                current_app.logger.exception('Failed to send new password email (POST fallback)')
                notifications['email']['sent'] = False
                notifications['email']['error'] = str(e)

        if send_sms:
            notifications['sms']['sent'] = False
            notifications['sms']['error'] = 'SMS delivery not implemented'

        try:
            generate_students_json()
        except Exception:
            current_app.logger.exception('Failed to regenerate students.json after update (POST fallback)')
        return {"success": True, "id": student.id, "notifications": notifications}, 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to update student (POST fallback)')
        return {"success": False, "error": "Update failed", "detail": str(e), "code": 500}, 500


@bp.route("/students/<int:student_id>", methods=["DELETE"])
@jwt_required()
@limiter.limit("30/minute")
def delete_student(student_id):
    """Delete a student record from the database. Admin only."""
    # Check if user is admin
    claims = get_jwt()
    if not claims or claims.get('role') != 'admin':
        return {"success": False, "error": "Admin access required", "code": 403}, 403
    
    student = Student.query.get(student_id)
    if not student:
        return {"success": False, "error": "Student not found", "code": 404}, 404

    try:
        # Best-effort: also remove the associated auth User so the
        # student's credentials can no longer be used to log in.
        student_email = (student.email or '').strip().lower()
        user = None
        if student_email:
            try:
                user = User.query.filter(func.lower(User.email) == student_email).first()
            except Exception:
                # Fallback for DBs without func.lower support
                user = User.query.filter(User.email.ilike(student_email)).first()

        if user:
            # Remove any progress rows tied to this user to avoid
            # foreign-key issues and stale leaderboard data.
            try:
                Progress.query.filter_by(user_id=user.id).delete(synchronize_session=False)
            except Exception:
                current_app.logger.exception('Failed to delete Progress rows for user %s during student delete', user.id)
            db.session.delete(user)

        db.session.delete(student)
        db.session.commit()

        # Regenerate students JSON
        try:
            generate_students_json()
        except Exception:
            current_app.logger.exception('Failed to regenerate students.json after delete')
        return {"success": True, "id": student_id}, 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to delete student')
        return {"success": False, "error": "Delete failed", "detail": str(e), "code": 500}, 500


@bp.route("/students/<int:student_id>/delete", methods=["POST"])
@jwt_required()
@limiter.limit("30/minute")
def delete_student_fallback_post(student_id):
    """Fallback delete endpoint for environments where DELETE is blocked upstream.

    Performs the same admin check and deletion as the DELETE route.
    """
    claims = get_jwt()
    if not claims or claims.get('role') != 'admin':
        return {"success": False, "error": "Admin access required", "code": 403}, 403

    student = Student.query.get(student_id)
    if not student:
        return {"success": False, "error": "Student not found", "code": 404}, 404

    try:
        # Mirror the DELETE logic: remove linked auth user + progress.
        student_email = (student.email or '').strip().lower()
        user = None
        if student_email:
            try:
                user = User.query.filter(func.lower(User.email) == student_email).first()
            except Exception:
                user = User.query.filter(User.email.ilike(student_email)).first()

        if user:
            try:
                Progress.query.filter_by(user_id=user.id).delete(synchronize_session=False)
            except Exception:
                current_app.logger.exception('Failed to delete Progress rows for user %s during student delete (POST fallback)', user.id)
            db.session.delete(user)

        db.session.delete(student)
        db.session.commit()
        try:
            generate_students_json()
        except Exception:
            current_app.logger.exception('Failed to regenerate students.json after delete (POST fallback)')
        return {"success": True, "id": student_id}, 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to delete student (POST fallback)')
        return {"success": False, "error": "Delete failed", "detail": str(e), "code": 500}, 500

@bp.route('/whoami', methods=['GET'])
@jwt_required()
def whoami():
    try:
        claims = get_jwt() or {}
        identity = get_jwt_identity()
        return {
            'success': True,
            'identity': identity,
            'claims': claims
        }, 200
    except Exception as e:
        return {'success': False, 'error': str(e)}, 500


@bp.route("/students/<int:student_id>/avatar", methods=["GET"])
@limiter.limit("60/minute")
def get_student_avatar(student_id):
    """Get/serve avatar image for a student.
    
    Returns the image file directly for display in browser/img tags.
    """
    student = Student.query.get(student_id)
    if not student:
        return {"success": False, "error": "Student not found", "code": 404}, 404
    
    if not student.image:
        return {"success": False, "error": "Student has no avatar", "code": 404}, 404
    
    try:
        # Get file path - handle both absolute and relative paths
        upload_base = current_app.config.get('UPLOAD_PATH', 'uploads')
        
        # If upload_base is not absolute, make it relative to project root
        if not Path(upload_base).is_absolute():
            # Get project root (parent of app folder)
            project_root = Path(current_app.root_path).parent
            upload_base = project_root / upload_base
        
        file_path = Path(upload_base) / student.image.lstrip('/')
        
        if not file_path.exists():
            return {"success": False, "error": "Avatar file not found", "code": 404}, 404
        
        # Serve the file
        return send_file(str(file_path), mimetype='image/png')
        
    except Exception as e:
        current_app.logger.exception('Failed to retrieve avatar')
        return {"success": False, "error": "Failed to retrieve avatar", "detail": str(e), "code": 500}, 500


@bp.route("/students/<int:student_id>/avatar", methods=["POST"])
@limiter.limit("10/minute")
def upload_student_avatar(student_id):
    """Upload avatar image for a student.
    
    Expects multipart/form-data with 'avatar' file field.
    Allowed extensions: jpg, jpeg, png, gif
    Max file size: 5MB
    
    Returns:
    {
        "success": true,
        "image_path": "/avatars/student_123_avatar.jpg"
    }
    """
    student = Student.query.get(student_id)
    if not student:
        return {"success": False, "error": "Student not found", "code": 404}, 404
    
    # Check if file is present in request
    if 'avatar' not in request.files:
        return {"success": False, "error": "No avatar file provided", "code": 400}, 400
    
    file = request.files['avatar']
    
    # Check if filename is empty
    if file.filename == '':
        return {"success": False, "error": "No file selected", "code": 400}, 400
    
    # Validate file extension
    allowed_extensions = {'jpg', 'jpeg', 'png', 'gif'}
    filename = secure_filename(file.filename)
    file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    if file_ext not in allowed_extensions:
        return {"success": False, "error": f"Invalid file type. Allowed: {', '.join(allowed_extensions)}", "code": 400}, 400
    
    # Check file size (5MB max)
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)  # Reset file pointer
    
    if file_size > 5 * 1024 * 1024:  # 5MB
        return {"success": False, "error": "File too large. Maximum size: 5MB", "code": 400}, 400
    
    try:
        # Create avatars directory if it doesn't exist
        upload_base = current_app.config.get('UPLOAD_PATH', 'uploads')
        
        # If upload_base is not absolute, make it relative to project root
        if not Path(upload_base).is_absolute():
            # Get project root (parent of app folder)
            project_root = Path(current_app.root_path).parent
            upload_base = project_root / upload_base
        
        avatars_dir = Path(upload_base) / 'avatars'
        avatars_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        new_filename = f"student_{student_id}_avatar.{file_ext}"
        file_path = avatars_dir / new_filename
        
        # Delete old avatar if exists
        if student.image:
            old_file_path = Path(upload_base) / student.image.lstrip('/')
            if old_file_path.exists():
                try:
                    old_file_path.unlink()
                except Exception:
                    current_app.logger.warning(f'Failed to delete old avatar: {old_file_path}')
        
        # Save new file
        file.save(str(file_path))
        
        # Update database with relative path
        relative_path = f"/avatars/{new_filename}"
        student.image = relative_path
        db.session.commit()
        
        # Regenerate students JSON
        try:
            generate_students_json()
        except Exception:
            current_app.logger.exception('Failed to regenerate students.json after avatar upload')
        
        return {"success": True, "image_path": relative_path}, 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to upload avatar')
        return {"success": False, "error": "Upload failed", "detail": str(e), "code": 500}, 500


@bp.route("/students/<int:student_id>/avatar", methods=["DELETE"])
@limiter.limit("10/minute")
def delete_student_avatar(student_id):
    """Delete avatar image for a student."""
    student = Student.query.get(student_id)
    if not student:
        return {"success": False, "error": "Student not found", "code": 404}, 404
    
    if not student.image:
        return {"success": False, "error": "Student has no avatar", "code": 404}, 404
    
    try:
        # Delete file from filesystem
        upload_base = current_app.config.get('UPLOAD_PATH', 'uploads')
        
        # If upload_base is not absolute, make it relative to project root
        if not Path(upload_base).is_absolute():
            # Get project root (parent of app folder)
            project_root = Path(current_app.root_path).parent
            upload_base = project_root / upload_base
        
        file_path = Path(upload_base) / student.image.lstrip('/')
        
        if file_path.exists():
            file_path.unlink()
        
        # Clear image field in database
        student.image = None
        db.session.commit()
        
        # Regenerate students JSON
        try:
            generate_students_json()
        except Exception:
            current_app.logger.exception('Failed to regenerate students.json after avatar delete')
        
        return {"success": True}, 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to delete avatar')
        return {"success": False, "error": "Delete failed", "detail": str(e), "code": 500}, 500




