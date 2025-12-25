from flask import Blueprint, request, jsonify, current_app
from .extensions import db, jwt, limiter
from .models import User
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/register", methods=["POST"])
@limiter.limit("5 per minute")
def register():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")
    role = data.get("role", "student")
    if not email or not password:
        return {"success": False, "error": "email and password required", "code": 400}, 400
    user = User(email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {"success": False, "error": "email already exists", "code": 400}, 400
    access = create_access_token(identity=str(user.id))
    refresh = create_refresh_token(identity=str(user.id))
    return {"success": True, "access_token": access, "refresh_token": refresh, "expires_in": current_app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds()}

@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        return {"success": False, "error": "email and password required", "code": 400}, 400
    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return {"success": False, "error": "invalid credentials", "code": 401}, 401
    access = create_access_token(identity=str(user.id))
    refresh = create_refresh_token(identity=str(user.id))
    return {"success": True, "access_token": access, "refresh_token": refresh, "expires_in": current_app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds()}

# Example protected route (for manual testing)
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    identity = get_jwt_identity()
    return {"success": True, "user": identity}
