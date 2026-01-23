from datetime import datetime
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from sqlalchemy import Index
from .extensions import db
from werkzeug.security import generate_password_hash, check_password_hash

# Column for JSON detection: fallback to Text if MySQL < 5.7 is used is left to SQLA dialect.
JSON_COL = MySQLJSON

class User(db.Model):  # type: ignore[name-defined]
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum("student","teacher","admin", name="user_roles"), default="student", nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Course(db.Model):  # type: ignore[name-defined]
    __tablename__ = "courses"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), index=True, nullable=False)
    description = db.Column(db.Text)
    # Extended fields for admin-managed course metadata
    thumbnail_url = db.Column(db.String(1024), nullable=True)
    # optional FK to an Asset row for the thumbnail
    thumbnail_asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=True)
    category = db.Column(db.String(100), nullable=True, index=True)
    class_name = db.Column(db.String(50), nullable=True, index=True)
    price = db.Column(db.Integer, nullable=True)
    published = db.Column(db.Boolean, default=False, index=True)
    featured = db.Column(db.Boolean, default=False)
    duration_weeks = db.Column(db.Integer, nullable=True)
    weekly_hours = db.Column(db.Integer, nullable=True)
    difficulty = db.Column(db.Enum('beginner','intermediate','advanced', name='course_difficulty'), nullable=True, index=True)
    stream = db.Column(db.String(50), nullable=True)
    tags = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    # relationship to the Asset model (nullable)
    thumbnail_asset = db.relationship('Asset', foreign_keys=[thumbnail_asset_id])

class Lesson(db.Model):  # type: ignore[name-defined]
    __tablename__ = "lessons"
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), index=True, nullable=False)
    title = db.Column(db.String(255), nullable=False, index=True)
    # store optional rich/structured content; legacy clients may still use this
    content_json = db.Column(JSON_COL, nullable=True)
    # convenience columns derived from admin UI fields in lesson.html
    description = db.Column(db.Text, nullable=True)
    duration = db.Column(db.Integer, nullable=True)
    level = db.Column(db.String(50), nullable=True, index=True)
    objectives = db.Column(db.Text, nullable=True)
    content_version = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    course = db.relationship("Course", backref=db.backref("lessons", lazy="dynamic"))

class Topic(db.Model):  # type: ignore[name-defined]
    __tablename__ = "topics"
    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id"), index=True, nullable=False)
    title = db.Column(db.String(255))
    data_json = db.Column(JSON_COL)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

class Asset(db.Model):  # type: ignore[name-defined]
    __tablename__ = "assets"
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(1024), nullable=False)
    # allow nullable uploader_id so anonymous uploads can be recorded
    uploader_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True, nullable=True)
    size = db.Column(db.Integer)
    mime_type = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    uploader = db.relationship("User")

class Progress(db.Model):  # type: ignore[name-defined]
    __tablename__ = "progress"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True, nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id"), index=True, nullable=False)
    score = db.Column(db.Float)
    time_spent = db.Column(db.Integer)  # seconds
    answers = db.Column(JSON_COL)
    attempt_id = db.Column(db.String(255), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship("User")
    lesson = db.relationship("Lesson")

# Index examples (if you want explicit composite indexes)
Index("ix_progress_user_lesson", Progress.user_id, Progress.lesson_id)


class Student(db.Model):  # type: ignore[name-defined]
    """Optional student-specific table that links to a `User` record.

    This table may be present in some deployments. We keep it lightweight
    so APIs can prefer student-specific metadata when available while
    falling back to the `User` model for authentication.
    """
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=True)
    email = db.Column(db.String(255), nullable=True, index=True)
    password = db.Column(db.String(255), nullable=True)
    syllabus = db.Column(db.String(255), nullable=True)
    class_ = db.Column(db.String(50), nullable=True, name='class')
    courses = db.Column(db.Text, nullable=True)
    second_language = db.Column(db.String(100), nullable=True)
    third_language = db.Column(db.String(100), nullable=True)
    # Default enrollment date to now when not provided
    date = db.Column(db.DateTime, nullable=True, default=datetime.utcnow)
    # Status: active or inactive (admin can change this)
    status = db.Column(db.Enum('active', 'inactive', name='student_status'), default='active', nullable=False)
    # Avatar image path (stored in /uploads/avatars/)
    image = db.Column(db.String(255), nullable=True)
    # Mobile number (10 digits)
    mobile = db.Column(db.String(10), nullable=True)


class Staff(db.Model):  # type: ignore[name-defined]
    __tablename__ = "staff"

    id = db.Column(db.Integer, primary_key=True)
    # Optional link to a user account if you later unify auth under `users`
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    # Personal / Contact details
    name = db.Column(db.String(255), nullable=False)
    gender = db.Column(db.Enum("male", "female", "other", name="staff_gender"), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=False)
    city = db.Column(db.String(120), nullable=True)
    department = db.Column(db.String(100), nullable=True, index=True)

    # Role / Access
    role = db.Column(db.String(100), nullable=False, index=True)
    status = db.Column(db.Enum("active", "inactive", name="staff_status"), default="active", nullable=False, index=True)
    permissions = db.Column(JSON_COL, nullable=True)

    # Profile
    avatar = db.Column(db.String(1024), nullable=True)
    join_date = db.Column(db.Date, nullable=True)

    # Account
    password_hash = db.Column(db.String(255), nullable=True)
    send_email = db.Column(db.Boolean, default=True, nullable=False)
    send_sms = db.Column(db.Boolean, default=False, nullable=False)
    last_login_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)


class Notification(db.Model):  # type: ignore[name-defined]
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text, nullable=False)
    message = db.Column(db.Text, nullable=False)
    category = db.Column(db.Text, nullable=False)
    target = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, nullable=False)
    scheduled_at = db.Column(db.TIMESTAMP, nullable=True)
    created_at = db.Column(db.TIMESTAMP, nullable=False, default=datetime.utcnow, index=True)


class Leaderboard(db.Model):  # type: ignore[name-defined]
    """Leaderboard table storing ranked student data."""
    __tablename__ = 'leaderboard'
    id = db.Column(db.Integer, primary_key=True)
    rank = db.Column(db.Integer, index=True, nullable=False)
    name = db.Column(db.String(255), nullable=True)
    score = db.Column(db.Float, nullable=True, default=0.0)
    last_updated_date = db.Column(db.DateTime, nullable=True)
    league = db.Column(db.Enum('bronze', 'silver', 'gold', 'platinum', name='leaderboard_league'), nullable=True)


class Card(db.Model):  # type: ignore[name-defined]
    """Card table for storing concept, quiz, video, and interactive cards."""
    __tablename__ = 'cards'
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey('topics.id'), index=True, nullable=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), index=True, nullable=True)
    card_type = db.Column(db.Enum('concept', 'quiz', 'video', 'interactive', name='card_type'), nullable=False, index=True)
    title = db.Column(db.String(500), nullable=False)
    # JSON data storing card-specific content (blocks for concept, questions for quiz, etc.)
    data_json = db.Column(JSON_COL, nullable=True)
    # Display order within the topic/lesson
    display_order = db.Column(db.Integer, default=0, index=True)
    # Metadata
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published = db.Column(db.Boolean, default=False, index=True)
    
    # Relationships
    topic = db.relationship('Topic', backref=db.backref('cards', lazy='dynamic'))
    lesson = db.relationship('Lesson', backref=db.backref('cards', lazy='dynamic'))
    creator = db.relationship('User', foreign_keys=[created_by])

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'card_type': self.card_type,
            'data_json': self.data_json,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'published': self.published
        }
