from flask import request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt
from flask_jwt_extended import verify_jwt_in_request
from ..models import Card, Topic, Lesson, User
from ..extensions import db, limiter
from . import bp


@bp.route("/topics", methods=["POST"])
@jwt_required()
@limiter.limit("30/minute")
def create_topic():
    """Create a new topic for organizing cards.
    
    Expected JSON: {
        lesson_id: int,
        title: string,
        data_json?: object
    }
    """
    # Check if user is admin
    claims = get_jwt()
    if not claims or claims.get('role') != 'admin':
        return {"success": False, "error": "Admin access required", "code": 403}, 403
    
    data = request.get_json(silent=True)
    if not data:
        return {"success": False, "error": "JSON payload required", "code": 400}, 400
    
    lesson_id = data.get('lesson_id')
    title = data.get('title', '').strip()
    
    if not lesson_id:
        return {"success": False, "error": "lesson_id is required", "code": 400}, 400
    
    if not title:
        return {"success": False, "error": "title is required", "code": 400}, 400
    
    # Validate lesson exists
    lesson = Lesson.query.get(lesson_id)
    if not lesson:
        return {"success": False, "error": "Lesson not found", "code": 404}, 404
    
    try:
        new_topic = Topic(
            lesson_id=lesson_id,
            title=title,
            data_json=data.get('data_json', {})
        )
        
        db.session.add(new_topic)
        db.session.commit()
        
        return {
            "success": True,
            "id": new_topic.id,
            "topic": {
                "id": new_topic.id,
                "lesson_id": new_topic.lesson_id,
                "title": new_topic.title,
                "created_at": new_topic.created_at.isoformat() if new_topic.created_at else None
            }
        }, 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to create topic')
        return {"success": False, "error": "Failed to create topic", "detail": str(e), "code": 500}, 500


@bp.route("/cards", methods=["POST"])
@jwt_required()
@limiter.limit("30/minute")
def create_card():
    """Create a new card (concept, quiz, video, or interactive).
    
    Expected JSON: {
        card_type: 'concept'|'quiz'|'video'|'interactive',
        title: string,
        data_json: object (card-specific content),
        topic_id?: int,
        lesson_id?: int,
        display_order?: int
    }
    """
    # Check if user is admin
    claims = get_jwt()
    user_id = claims.get('sub')  # This is the identity (user_id string)
    
    if not claims or claims.get('role') != 'admin':
        return {"success": False, "error": "Admin access required", "code": 403}, 403
    
    data = request.get_json(silent=True)
    if not data:
        return {"success": False, "error": "JSON payload required", "code": 400}, 400
    
    card_type = data.get('card_type', '').strip().lower()
    title = data.get('title', '').strip()
    
    if card_type not in ['concept', 'quiz', 'video', 'interactive']:
        return {"success": False, "error": "Invalid card_type. Must be: concept, quiz, video, or interactive", "code": 400}, 400
    
    if not title:
        return {"success": False, "error": "Title is required", "code": 400}, 400
    
    topic_id = data.get('topic_id')
    lesson_id = data.get('lesson_id')
    
    # At least one of topic_id or lesson_id should be provided
    if not topic_id and not lesson_id:
        return {"success": False, "error": "Either topic_id or lesson_id is required", "code": 400}, 400
    
    # Validate that topic or lesson exists
    if topic_id:
        topic = Topic.query.get(topic_id)
        if not topic:
            return {"success": False, "error": "Topic not found", "code": 404}, 404
    
    if lesson_id:
        lesson = Lesson.query.get(lesson_id)
        if not lesson:
            return {"success": False, "error": "Lesson not found", "code": 404}, 404
    
    # Determine created_by safely to avoid FK errors if user id is invalid
    created_by_val = None
    if user_id and user_id != 'dev_admin':
        try:
            uid_int = int(user_id)
            if User.query.get(uid_int):
                created_by_val = uid_int
        except Exception:
            created_by_val = None

    try:
        # Business rule: all cards are published upon creation
        pub_norm = True

        new_card = Card(
            card_type=card_type,
            title=title,
            data_json=data.get('data_json', {}),
            topic_id=topic_id,
            lesson_id=lesson_id,
            display_order=data.get('display_order', 0),
            created_by=created_by_val,
            # Publish all newly created cards by design
            published=pub_norm
        )
        
        db.session.add(new_card)
        db.session.commit()
        
        return {
            "success": True,
            "id": new_card.id,
            "card": {
                "id": new_card.id,
                "card_type": new_card.card_type,
                "title": new_card.title,
                "topic_id": new_card.topic_id,
                "lesson_id": new_card.lesson_id,
                "display_order": new_card.display_order,
                "published": new_card.published,
                "created_at": new_card.created_at.isoformat() if new_card.created_at else None
            }
        }, 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to create card')
        detail = str(e)
        try:
            # Attempt to surface DB-level error messages when available
            from sqlalchemy.exc import SQLAlchemyError
            if isinstance(e, SQLAlchemyError) and getattr(e, 'orig', None):
                detail = f"{detail} | DB: {e.orig}"
        except Exception:
            pass
        return {"success": False, "error": "Failed to create card", "detail": detail, "code": 500}, 500


@bp.route("/cards", methods=["GET"])
def list_cards():
    """List cards with optional filters and pagination.

    Query params:
      - topic_id: int
      - lesson_id: int
      - card_type: concept|quiz|video|interactive
      - published: true|false
      - page: int (default 1)
      - per_page: int (default 20, max 100)
    """
    # Determine auth state; optional JWT
    is_authenticated = False
    try:
        verify_jwt_in_request(optional=True)
        claims = get_jwt() or {}
        is_authenticated = True if claims else False
    except Exception:
        is_authenticated = False

    # Build base query
    query = Card.query

    # Filters
    topic_id = request.args.get("topic_id", type=int)
    lesson_id = request.args.get("lesson_id", type=int)
    card_type = request.args.get("card_type", type=str)
    published = request.args.get("published", type=str)

    if topic_id is not None:
        query = query.filter(Card.topic_id == topic_id)
    if lesson_id is not None:
        query = query.filter(Card.lesson_id == lesson_id)
    if card_type:
        ct = card_type.strip().lower()
        if ct in ["concept", "quiz", "video", "interactive"]:
            query = query.filter(Card.card_type == ct)
        else:
            return {"success": False, "error": "Invalid card_type filter", "code": 400}, 400
    if published is not None:
        if published.lower() in ["true", "1", "yes"]:
            query = query.filter(Card.published.is_(True))
        elif published.lower() in ["false", "0", "no"]:
            query = query.filter(Card.published.is_(False))
        else:
            return {"success": False, "error": "Invalid published filter; use true/false", "code": 400}, 400

    # For unauthenticated requests, restrict results
    if not is_authenticated:
        # Only show published cards publicly
        query = query.filter(Card.published.is_(True))
        # Require at least one scoping filter to avoid listing all data
        if topic_id is None and lesson_id is None:
            return {
                "success": False,
                "error": "topic_id or lesson_id is required for public access",
                "code": 400
            }, 400

    # Ordering: display_order, created_at
    query = query.order_by(Card.display_order, Card.created_at)

    # Pagination
    page = request.args.get("page", default=1, type=int) or 1
    per_page = request.args.get("per_page", default=20, type=int) or 20
    per_page = max(1, min(per_page, 100))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    items = pagination.items

    return {
        "success": True,
        "page": page,
        "per_page": per_page,
        "total": pagination.total,
        "pages": pagination.pages,
        "data": [
            {
                "id": c.id,
                "card_type": c.card_type,
                "title": c.title,
                "topic_id": c.topic_id,
                "lesson_id": c.lesson_id,
                "display_order": c.display_order,
                "published": c.published,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in items
        ],
    }, 200


@bp.route("/cards/<int:card_id>", methods=["GET"])
def get_card(card_id):
    """Get a specific card by ID.

    Publicly accessible: unauthenticated users may fetch only published cards.
    Authenticated users can fetch any card (subject to existence).
    """
    # Optional auth; detect whether a JWT is present
    is_authenticated = False
    try:
        verify_jwt_in_request(optional=True)
        claims = get_jwt() or {}
        is_authenticated = True if claims else False
    except Exception:
        is_authenticated = False

    card = Card.query.get(card_id)
    if not card:
        return {"success": False, "error": "Card not found", "code": 404}, 404

    # If not authenticated, only allow access to published cards
    if not is_authenticated and not card.published:
        return {"success": False, "error": "Card is not published", "code": 403}, 403

    return {
        "success": True,
        "card": {
            "id": card.id,
            "card_type": card.card_type,
            "title": card.title,
            "data_json": card.data_json,
            "topic_id": card.topic_id,
            "lesson_id": card.lesson_id,
            "display_order": card.display_order,
            "published": card.published,
            "created_at": card.created_at.isoformat() if card.created_at else None,
            "updated_at": card.updated_at.isoformat() if card.updated_at else None
        }
    }, 200


@bp.route("/cards/<int:card_id>", methods=["PUT"])
@jwt_required()
@limiter.limit("30/minute")
def update_card(card_id):
    """Update an existing card.
    
    Expected JSON: {
        title?: string,
        data_json?: object,
        display_order?: int,
        published?: bool
    }
    """
    # Check if user is admin
    claims = get_jwt()
    if not claims or claims.get('role') != 'admin':
        return {"success": False, "error": "Admin access required", "code": 403}, 403
    
    data = request.get_json(silent=True)
    if not data:
        return {"success": False, "error": "JSON payload required", "code": 400}, 400
    
    card = Card.query.get(card_id)
    if not card:
        return {"success": False, "error": "Card not found", "code": 404}, 404
    
    try:
        # Update fields if provided
        if 'title' in data:
            card.title = data['title']
        if 'data_json' in data:
            card.data_json = data['data_json']
        if 'display_order' in data:
            card.display_order = data['display_order']
        if 'published' in data:
            card.published = bool(data['published'])
        
        db.session.commit()
        
        return {
            "success": True,
            "id": card.id,
            "card": {
                "id": card.id,
                "card_type": card.card_type,
                "title": card.title,
                "topic_id": card.topic_id,
                "lesson_id": card.lesson_id,
                "display_order": card.display_order,
                "published": card.published,
                "updated_at": card.updated_at.isoformat() if card.updated_at else None
            }
        }, 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to update card')
        return {"success": False, "error": "Failed to update card", "detail": str(e), "code": 500}, 500


@bp.route("/cards/<int:card_id>", methods=["DELETE"])
@jwt_required()
@limiter.limit("30/minute")
def delete_card(card_id):
    """Delete a card. Admin only."""
    # Check if user is admin
    claims = get_jwt()
    if not claims or claims.get('role') != 'admin':
        return {"success": False, "error": "Admin access required", "code": 403}, 403
    
    card = Card.query.get(card_id)
    if not card:
        return {"success": False, "error": "Card not found", "code": 404}, 404
    
    try:
        db.session.delete(card)
        db.session.commit()
        return {"success": True, "id": card_id}, 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to delete card')
        return {"success": False, "error": "Failed to delete card", "detail": str(e), "code": 500}, 500


@bp.route("/topics/<int:topic_id>/cards", methods=["GET"])
def get_topic_cards(topic_id):
    """Get all cards for a specific topic."""
    topic = Topic.query.get(topic_id)
    if not topic:
        return {"success": False, "error": "Topic not found", "code": 404}, 404
    
    # Optional auth; unauthenticated users see only published
    is_authenticated = False
    try:
        verify_jwt_in_request(optional=True)
        claims = get_jwt() or {}
        is_authenticated = True if claims else False
    except Exception:
        is_authenticated = False

    q = Card.query.filter_by(topic_id=topic_id)
    if not is_authenticated:
        q = q.filter(Card.published.is_(True))
    cards = q.order_by(Card.display_order, Card.created_at).all()
    
    return {
        "success": True,
        "topic_id": topic_id,
        "cards": [
            {
                "id": card.id,
                "card_type": card.card_type,
                "title": card.title,
                "display_order": card.display_order,
                "published": card.published,
                "created_at": card.created_at.isoformat() if card.created_at else None
            }
            for card in cards
        ]
    }, 200


@bp.route("/lessons/<int:lesson_id>/cards", methods=["GET"])
def get_lesson_cards(lesson_id):
    """Get all cards for a specific lesson."""
    lesson = Lesson.query.get(lesson_id)
    if not lesson:
        return {"success": False, "error": "Lesson not found", "code": 404}, 404
    
    # Optional auth; unauthenticated users see only published
    is_authenticated = False
    try:
        verify_jwt_in_request(optional=True)
        claims = get_jwt() or {}
        is_authenticated = True if claims else False
    except Exception:
        is_authenticated = False

    q = Card.query.filter_by(lesson_id=lesson_id)
    if not is_authenticated:
        q = q.filter(Card.published.is_(True))
    cards = q.order_by(Card.display_order, Card.created_at).all()
    
    return {
        "success": True,
        "lesson_id": lesson_id,
        "cards": [
            {
                "id": card.id,
                "card_type": card.card_type,
                "title": card.title,
                "display_order": card.display_order,
                "published": card.published,
                "created_at": card.created_at.isoformat() if card.created_at else None
            }
            for card in cards
        ]
    }, 200
