from flask import request, jsonify, current_app
from ..models import Course, Lesson, Topic, Card
from ..extensions import db
from . import bp


@bp.route("/courses", methods=["GET"])
def list_courses():
    # pagination
    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))
    except ValueError:
        page, limit = 1, 20

    q = Course.query
    # filters (title)
    title = request.args.get("title")
    if title:
        q = q.filter(Course.title.ilike(f"%{title}%"))

    # Use full Course rows so we can include extra attributes and counts
    items = q.order_by(Course.created_at.desc()).paginate(page=page, per_page=limit, error_out=False)

    data = []
    for c in items.items:
        # Aggregate counts for each course (same logic as get_course)
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
                # match shape of single-course API
                "class_name": getattr(c, "class_name", None),
                "category": getattr(c, "category", None),
                "totalLessons": int(total_lessons),
                "totalTopics": int(total_topics),
                "totalCards": int(total_cards),
            }
        )

    return {"success": True, "data": data, "meta": {"page": items.page, "pages": items.pages, "total": items.total}}

@bp.route("/courses/<int:id>", methods=["GET"])
def get_course(id):
    # Load full course row so we can expose more attributes
    c = Course.query.filter_by(id=id).first_or_404()

    # Aggregate counts for this course
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

    data = {
        "id": c.id,
        "title": c.title,
        "description": c.description,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        # direct course attributes commonly needed by clients
        "class_name": getattr(c, "class_name", None),
        "category": getattr(c, "category", None),
        # aggregated counts for this course
        "totalLessons": int(total_lessons),
        "totalTopics": int(total_topics),
        "totalCards": int(total_cards),
    }

    return {"success": True, "data": data}

@bp.route("/courses/<int:id>/lessons", methods=["GET"])
def get_course_lessons(id):
    # load full lessons for this course so we can derive extra attributes
    lessons = Lesson.query.filter_by(course_id=id).order_by(Lesson.created_at.asc()).all()

    data = []
    for l in lessons:
        # derive order, icon, and description from content_json (if present)
        meta = l.content_json if isinstance(getattr(l, "content_json", None), dict) else {}
        order_val = None
        meta_description = None
        meta_icon = None
        if isinstance(meta, dict):
            if meta.get("order") is not None:
                try:
                    order_val = int(meta.get("order"))
                except Exception:
                    order_val = meta.get("order")
            meta_description = meta.get("description")
            meta_icon = meta.get("icon")

        topic_count = Topic.query.filter_by(lesson_id=l.id).count()
        card_count = Card.query.filter_by(lesson_id=l.id).count()

        data.append(
            {
                "id": l.id,
                "course_id": l.course_id,
                "title": l.title,
                "content_version": getattr(l, "content_version", None),
                "created_at": l.created_at.isoformat() if l.created_at else None,
                # extra attributes requested
                "description": meta_description or (l.description or ""),
                "order": order_val,
                # estimated_time in JSON should mirror DB column `duration`
                "estimated_time": getattr(l, "duration", None),
                "topicCount": int(topic_count),
                "cardCount": int(card_count),
                "icon": meta_icon,
            }
        )

    return {"success": True, "data": data}


@bp.route("/courses/<int:id>/publish", methods=["POST"])
def publish_course(id):
    """Publish a course and return updated course metadata.

    This sets Course.published = True for the given course id and returns
    the same enriched payload shape as GET /courses/<id>.
    """
    # Find the course
    course = Course.query.filter_by(id=id).first()
    if not course:
        return {"success": False, "error": "Course not found"}, 404

    # Mark as published
    course.published = True
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to publish course")
        return {"success": False, "error": "Failed to publish course"}, 500

    # Reuse the same aggregation logic as get_course
    lessons = Lesson.query.filter_by(course_id=course.id).all()
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

    data = {
        "id": course.id,
        "title": course.title,
        "description": course.description,
        "created_at": course.created_at.isoformat() if course.created_at else None,
        "class_name": getattr(course, "class_name", None),
        "category": getattr(course, "category", None),
        "published": getattr(course, "published", None),
        "totalLessons": int(total_lessons),
        "totalTopics": int(total_topics),
        "totalCards": int(total_cards),
    }

    return {"success": True, "data": data}, 200


@bp.route("/courses/<int:id>/publish", methods=["GET"])
def get_course_publish_status(id):
    """Return publish metadata for a course without modifying it.

    This mirrors the payload shape returned by POST /courses/<id>/publish
    but only reads the current Course.published flag and aggregates.
    """
    course = Course.query.filter_by(id=id).first()
    if not course:
        return {"success": False, "error": "Course not found"}, 404

    # Aggregate same stats as publish_course
    lessons = Lesson.query.filter_by(course_id=course.id).all()
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

    data = {
        "id": course.id,
        "title": course.title,
        "description": course.description,
        "created_at": course.created_at.isoformat() if course.created_at else None,
        "class_name": getattr(course, "class_name", None),
        "category": getattr(course, "category", None),
        "published": getattr(course, "published", None),
        "totalLessons": int(total_lessons),
        "totalTopics": int(total_topics),
        "totalCards": int(total_cards),
    }

    return {"success": True, "data": data}, 200
