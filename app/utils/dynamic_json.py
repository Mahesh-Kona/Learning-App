import os
import json
import tempfile
from flask import current_app
from app.extensions import db


def _base_dir():
    d = os.path.join(current_app.instance_path, 'dynamic_json')
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        # best-effort
        pass
    return d


def _atomic_write(path, data):
    # Write JSON atomically
    tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path))
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        # replace
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


def write_json(filename, data):
    try:
        base = _base_dir()
        path = os.path.join(base, filename)
        _atomic_write(path, data)
        return True
    except Exception:
        current_app.logger.exception('Failed to write dynamic json %s', filename)
        return False


def generate_courses_json():
    from app.models import Course, Lesson

    try:
        courses_q = Course.query.order_by(Course.title).all()
        out = []
        for c in courses_q:
            lessons_count = 0
            try:
                lessons_count = Lesson.query.filter_by(course_id=c.id).count()
            except Exception:
                lessons_count = 0
            out.append({
                'id': c.id,
                'title': c.title or '',
                'description': c.description or '',
                'category': c.category or None,
                'thumbnail_url': c.thumbnail_url,
                'difficulty': c.difficulty,
                'duration_weeks': c.duration_weeks,
                'total_lessons': lessons_count,
                'published': getattr(c, 'published', False)
            })

        write_json('courses.json', {'courses': out})
        return True
    except Exception:
        current_app.logger.exception('Failed to generate courses.json')
        return False


def generate_course_lessons_json(course_id):
    from app.models import Lesson

    try:
        lessons_q = Lesson.query.filter_by(course_id=course_id).order_by(Lesson.created_at.desc()).all()
        lessons = [
            {
                'id': l.id,
                'title': l.title,
                'description': l.description or '',
                'duration': l.duration,
                'level': l.level,
            }
            for l in lessons_q
        ]

        write_json(f'course_{course_id}_lessons.json', {'course_id': course_id, 'lessons': lessons})
        return True
    except Exception:
        current_app.logger.exception('Failed to generate course_%s_lessons.json', course_id)
        return False


def generate_lesson_topics_json(lesson_id):
    from app.models import Topic

    try:
        topics_q = Topic.query.filter_by(lesson_id=lesson_id).order_by(Topic.id).all()
        topics = []
        for t in topics_q:
            data = t.data_json if isinstance(t.data_json, dict) else {}
            topics.append({
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

        write_json(f'lesson_{lesson_id}_topics.json', {'lesson_id': lesson_id, 'topics': topics})
        return True
    except Exception:
        current_app.logger.exception('Failed to generate lesson_%s_topics.json', lesson_id)
        return False


def generate_user_progress_json(user_id):
    from app.models import Progress, Lesson, Topic, Course

    try:
        # Build basic progress summary for user
        progress_rows = Progress.query.filter_by(user_id=user_id).all()
        # Map lesson_id -> progress
        lessons_map = {}
        for p in progress_rows:
            lessons_map[p.lesson_id] = {
                'lesson_id': p.lesson_id,
                'time_spent': p.time_spent or 0,
                'score': p.score,
                'answers': p.answers,
                'attempt_id': getattr(p, 'attempt_id', None),
                'updated_at': p.created_at.isoformat() if getattr(p, 'created_at', None) else None
            }

        # For convenience include enrolled courses / summary of completed lessons per course
        courses = {}
        for lid, info in lessons_map.items():
            try:
                lesson = Lesson.query.get(lid)
                if not lesson:
                    continue
                cid = lesson.course_id
                if cid not in courses:
                    courses[cid] = {'course_id': cid, 'completed_lessons': 0, 'time_spent': 0}
                courses[cid]['completed_lessons'] += 1
                courses[cid]['time_spent'] += info['time_spent']
            except Exception:
                continue

        courses_list = list(courses.values())

        payload = {
            'user_id': user_id,
            'lessons': list(lessons_map.values()),
            'course_summary': courses_list,
            'updated_at': datetime_now_iso()
        }

        write_json(f'user_{user_id}_progress.json', payload)
        return True
    except Exception:
        current_app.logger.exception('Failed to generate user_%s_progress.json', user_id)
        return False


def generate_user_profile_json(user_id):
    """Generate a mirror of the user's profile into `instance/dynamic_json/user_<id>_profile.json`.

    This prefers `Student` model if present, falls back to `Profile` then `User`.
    """
    try:
        from app.models import Student, Profile, User

        data = None
        # Try Student model first
        if 'Student' in globals() or True:
            try:
                Student = getattr(__import__('app.models', fromlist=['Student']), 'Student')
            except Exception:
                Student = None

        try:
            Profile = getattr(__import__('app.models', fromlist=['Profile']), 'Profile')
        except Exception:
            Profile = None

        try:
            User = getattr(__import__('app.models', fromlist=['User']), 'User')
        except Exception:
            User = None

        # Build profile-like dict
        profile = None
        if Student:
            try:
                profile = Student.query.filter_by(user_id=user_id).first() or Student.query.get(user_id)
            except Exception:
                profile = None

        if not profile and Profile:
            try:
                profile = Profile.query.filter_by(user_id=user_id).first()
            except Exception:
                profile = None

        if not profile and User:
            try:
                u = User.query.get(user_id)
                if u:
                    profile = type('P', (), {})()
                    setattr(profile, 'id', None)
                    setattr(profile, 'user_id', user_id)
                    setattr(profile, 'name', getattr(u, 'email', None))
                    setattr(profile, 'email', getattr(u, 'email', None))
                    setattr(profile, 'phone', None)
                    setattr(profile, 'bio', None)
                    setattr(profile, 'avatar_url', None)
                    setattr(profile, 'date_of_birth', None)
                    setattr(profile, 'grade', None)
                    setattr(profile, 'school', None)
                    setattr(profile, 'created_at', None)
                    setattr(profile, 'updated_at', None)
            except Exception:
                profile = None

        if not profile:
            return False

        resp = {
            'id': getattr(profile, 'id', None),
            'user_id': getattr(profile, 'user_id', None),
            'name': getattr(profile, 'name', None) or getattr(profile, 'display_name', None),
            'email': getattr(profile, 'email', None),
            'phone': getattr(profile, 'phone', None),
            'bio': getattr(profile, 'bio', None),
            'avatar_url': getattr(profile, 'avatar_url', None),
            'date_of_birth': getattr(profile, 'date_of_birth', None),
            'grade': getattr(profile, 'grade', None),
            'school': getattr(profile, 'school', None),
            'created_at': getattr(profile, 'created_at', None).isoformat() if getattr(profile, 'created_at', None) else None,
            'updated_at': getattr(profile, 'updated_at', None).isoformat() if getattr(profile, 'updated_at', None) else None
        }

        write_json(f'user_{user_id}_profile.json', {'profile': resp})
        return True
    except Exception:
        current_app.logger.exception('Failed to generate user_%s_profile.json', user_id)
        return False


def generate_user_notifications_json(user_id):
    """Generate a per-user notifications JSON file at
    `instance/dynamic_json/user_<id>_notifications.json`.
    """
    try:
        from app.models import Notification

        target_value = f'user:{int(user_id)}'
        try:
            notif_q = Notification.query.filter_by(target=target_value).order_by(Notification.created_at.desc()).all()
        except Exception:
            notif_q = []
        out = []
        for n in notif_q:
            out.append({
                'id': n.id,
                'title': n.title,
                'message': getattr(n, 'message', None),
                'category': getattr(n, 'category', None),
                'target': getattr(n, 'target', None),
                'status': getattr(n, 'status', None),
                'scheduled_at': n.scheduled_at.isoformat() if getattr(n, 'scheduled_at', None) else None,
                'created_at': n.created_at.isoformat() if getattr(n, 'created_at', None) else None
            })

        write_json(f'user_{user_id}_notifications.json', {'notifications': out})
        return True
    except Exception:
        current_app.logger.exception('Failed to generate user_%s_notifications.json', user_id)
        return False


def datetime_now_iso():
    try:
        from datetime import datetime
        return datetime.utcnow().isoformat()
    except Exception:
        return None


def generate_students_json():
    """Generate a list of all students into `instance/dynamic_json/students.json`."""
    try:
        from app.models import Student

        students_q = Student.query.order_by(Student.id.asc()).all()
        students_list = []
        
        for s in students_q:
            enrollment_date = ""
            if s.date:
                try:
                    enrollment_date = s.date.strftime('%Y-%m-%d')
                except:
                    enrollment_date = ""
            
            students_list.append({
                'id': s.id,
                'name': s.name or 'Unknown',
                'email': s.email or '',
                'enrollmentDate': enrollment_date,
                'courses': (getattr(s, 'courses', None) or getattr(s, 'subjects', None) or ''),
                'progress': 0,
                'xp': 0,
                'lastLogin': '',
                'status': 'active'
            })

        write_json('students.json', {'students': students_list, 'total': len(students_list)})
        return True
    except Exception:
        current_app.logger.exception('Failed to generate students.json')
        return False


def generate_all_jsons():
    # regenerate all top-level files (courses + per-course/per-lesson as available)
    try:
        generate_courses_json()
        generate_students_json()
        # Optionally generate per-course lessons by scanning courses
        from app.models import Course, Lesson, Topic
        courses = Course.query.all()
        for c in courses:
            try:
                generate_course_lessons_json(c.id)
            except Exception:
                continue
        # generate all lesson topics
        lessons = Lesson.query.all()
        for l in lessons:
            try:
                generate_lesson_topics_json(l.id)
            except Exception:
                continue
        return True
    except Exception:
        current_app.logger.exception('Failed to generate all dynamic jsons')
        return False
