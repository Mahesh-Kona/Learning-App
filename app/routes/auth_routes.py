from flask import Blueprint, request, jsonify, current_app
from app.extensions import db, limiter
from app.models import User, Student, Leaderboard
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity
from datetime import datetime
from sqlalchemy import func
from app.utils.dynamic_json import generate_students_json

auth_bp = Blueprint('auth_bp', __name__)


def update_leaderboard():
    """Recalculate and update leaderboard rankings based on scores.
    
    Ranks students by score (descending), then alphabetically by name.
    Only includes students who have attempted quizzes (score > 0).
    """
    try:
        # Get all students with their total scores from progress table
        from app.models import Progress
        
        # Calculate total score per student from progress table - only students with progress
        student_scores = db.session.query(
            Student.id,
            Student.name,
            Student.email,
            func.sum(Progress.score).label('total_score')
        ).join(
            Progress, Student.id == Progress.user_id
        ).group_by(
            Student.id, Student.name, Student.email
        ).having(
            func.sum(Progress.score) > 0
        ).order_by(
            func.sum(Progress.score).desc(),
            Student.name.asc()
        ).all()
        
        # Clear existing leaderboard
        Leaderboard.query.delete()
        
        # Insert new rankings
        for rank, (student_id, name, email, score) in enumerate(student_scores, start=1):
            leaderboard_entry = Leaderboard(
                rank=rank,
                name=name or 'Unknown',
                email=email or '',
                score=float(score or 0),
                last_updated_date=datetime.utcnow(),
                league=assign_league(score)
            )
            db.session.add(leaderboard_entry)
        
        db.session.commit()
        current_app.logger.info('Leaderboard updated successfully')
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to update leaderboard')


def assign_league(score):
    """Assign league based on score thresholds."""
    if score >= 900:
        return 'platinum'
    elif score >= 700:
        return 'gold'
    elif score >= 400:
        return 'silver'
    else:
        return 'bronze'


@auth_bp.route('/api/v1/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    if not data.get('email') or not data.get('password'):
        return jsonify({"success": False, "error": "Email and password required", "code": 400}), 400

    if User.query.filter_by(email=data['email']).first():
        return jsonify({"success": False, "error": "Email already registered", "code": 400}), 400

    # Check if student with same email exists
    if Student.query.filter_by(email=data['email']).first():
        return jsonify({"success": False, "error": "Email already registered", "code": 400}), 400

    # Create User record
    new_user = User(email=data['email'], role=data.get('role', 'student'))
    new_user.set_password(data['password'])
    db.session.add(new_user)
    db.session.flush()  # Get user ID before committing
    
    # Create Student record if role is student
    if new_user.role == 'student':
        new_student = Student(
            name=data.get('name', data['email'].split('@')[0]),
            email=data['email'],
            password='',  # Password stored in User table
            syllabus=data.get('syllabus', ''),
            class_=data.get('class', ''),
            subjects=data.get('subjects', ''),
            second_language=data.get('second_language', ''),
            third_language=data.get('third_language', ''),
            date=datetime.utcnow()
        )
        db.session.add(new_student)
    
    db.session.commit()
    
    # Regenerate students JSON for cloud sync
    if new_user.role == 'student':
        try:
            generate_students_json()
        except Exception:
            current_app.logger.exception('Failed to regenerate students.json after registration')
    
    # Don't add to leaderboard on registration - only after first quiz attempt
    # Leaderboard will be populated when student submits progress
    
    # Return access + refresh tokens on registration
    access = create_access_token(identity=str(new_user.id), additional_claims={"role": new_user.role})
    refresh = create_refresh_token(identity=str(new_user.id), additional_claims={"role": new_user.role})
    return jsonify({"success": True, "message": "User registered successfully", "access_token": access, "refresh_token": refresh}), 201


@auth_bp.route('/api/v1/auth/login', methods=['POST'])
@limiter.limit("5/minute")
def login():
    data = request.get_json() or {}
    user = User.query.filter_by(email=data.get('email')).first()

    if not user or not user.check_password(data.get('password')):
        return jsonify({"success": False, "error": "Invalid email or password", "code": 401}), 401

    access_token = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims={"role": user.role})
    return jsonify({
        "success": True,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {"id": user.id, "email": user.email, "role": user.role}
    }), 200



@auth_bp.route('/api/v1/auth/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh_token():
    identity = get_jwt_identity()
    # issue a new access token
    access = create_access_token(identity=identity)
    return jsonify({"success": True, "access_token": access}), 200
