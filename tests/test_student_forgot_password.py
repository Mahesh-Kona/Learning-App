from datetime import datetime

from app.extensions import db
from app.models import Student
from app.routes.api import _STUDENT_RESET_OTP


def test_student_forgot_password_requires_email(client):
    rv = client.post("/api/v1/auth/student/forgot-password", json={})
    assert rv.status_code == 400
    data = rv.get_json()
    assert data["success"] is False
    assert "Email is required" in data.get("error", "")


def test_student_forgot_password_unknown_email(client):
    rv = client.post(
        "/api/v1/auth/student/forgot-password",
        json={"email": "noone@example.com"},
    )
    assert rv.status_code == 404
    data = rv.get_json()
    assert data["success"] is False
    assert "No student found" in data.get("error", "")


def test_student_forgot_password_creates_otp_for_student(client):
    # Create an active student in the test DB
    student = Student(email="student1@example.com", status="active")
    db.session.add(student)
    db.session.commit()

    rv = client.post(
        "/api/v1/auth/student/forgot-password",
        json={"email": "student1@example.com"},
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["success"] is True
    assert data.get("expires_in") == 10 * 60

    # Verify an OTP entry exists in the in-memory store
    info = _STUDENT_RESET_OTP.get(int(student.id))
    assert info is not None
    assert info.get("otp_hash")
    assert info.get("expires_at") and isinstance(info["expires_at"], datetime)
    assert info["expires_at"] > datetime.utcnow()
