from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import Student
from app.routes.api import _STUDENT_RESET_OTP


def _create_student(email: str = "reset1@example.com") -> Student:
    student = Student(email=email, status="active", password="oldpass")
    db.session.add(student)
    db.session.commit()
    return student


def test_student_reset_password_invalid_otp(client):
    _STUDENT_RESET_OTP.clear()
    student = _create_student("reset_invalid@example.com")

    # Store a different OTP than what we'll send
    otp_correct = "9999"
    _STUDENT_RESET_OTP[int(student.id)] = {
        "otp_hash": generate_password_hash(otp_correct),
        "expires_at": datetime.utcnow() + timedelta(minutes=10),
        "email": student.email,
    }

    rv = client.post(
        "/api/v1/auth/student/reset-password",
        json={
            "email": student.email,
            "otp": "1234",  # wrong OTP
            "new_password": "NewPass123",
            "confirm_password": "NewPass123",
        },
    )
    assert rv.status_code == 400
    data = rv.get_json()
    assert data["success"] is False
    assert "Invalid OTP" in data.get("error", "")


def test_student_reset_password_success(client):
    _STUDENT_RESET_OTP.clear()
    student = _create_student("reset_success@example.com")

    otp = "1234"
    new_password = "NewPass123"

    _STUDENT_RESET_OTP[int(student.id)] = {
        "otp_hash": generate_password_hash(otp),
        "expires_at": datetime.utcnow() + timedelta(minutes=10),
        "email": student.email,
    }

    rv = client.post(
        "/api/v1/auth/student/reset-password",
        json={
            "email": student.email,
            "otp": otp,
            "new_password": new_password,
            "confirm_password": new_password,
        },
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["success"] is True
    assert "Password updated successfully" in data.get("message", "")

    # Reload student from DB and verify password changed
    db.session.refresh(student)
    assert student.password == new_password

    # OTP entry should be cleared after successful reset
    assert _STUDENT_RESET_OTP.get(int(student.id)) is None


def test_student_reset_password_expired_otp(client):
    _STUDENT_RESET_OTP.clear()
    student = _create_student("reset_expired@example.com")

    otp = "5678"

    _STUDENT_RESET_OTP[int(student.id)] = {
        "otp_hash": generate_password_hash(otp),
        "expires_at": datetime.utcnow() - timedelta(minutes=1),  # already expired
        "email": student.email,
    }

    rv = client.post(
        "/api/v1/auth/student/reset-password",
        json={
            "email": student.email,
            "otp": otp,
            "new_password": "AnotherPass123",
            "confirm_password": "AnotherPass123",
        },
    )
    assert rv.status_code == 400
    data = rv.get_json()
    assert data["success"] is False
    assert "OTP expired" in data.get("error", "")

    # OTP should be removed when expired
    assert _STUDENT_RESET_OTP.get(int(student.id)) is None
