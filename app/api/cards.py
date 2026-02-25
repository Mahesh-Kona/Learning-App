import json
import os

from flask import request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt
from flask_jwt_extended import verify_jwt_in_request
from ..models import Card, Topic, Lesson, User
from ..extensions import db, limiter
from ..utils.image_utils import compress_images_in_json
from utils.upload import upload_base64_image_to_r2
from r2_client import s3, R2_BUCKET, CDN_BASE
from .text_parser import parse_blocks  # ✅ Added
from . import bp


def _normalize_url_for_storage(url: str) -> str:
    """Normalize a URL to the scheme-less form stored in image_url.

        Examples:
            - https://file.edusaint.in/images/x.jpg -> file.edusaint.in/images/x.jpg
            - http://file.edusaint.in/images/x.jpg  -> file.edusaint.in/images/x.jpg
            - /uploads/foo.png                      -> file.edusaint.in/images/foo.png
    """
    if not isinstance(url, str) or not url:
        return ""
    url = url.strip()

    # If full URL, drop the scheme and keep host/path
    if url.startswith("http://") or url.startswith("https://"):
        return url.split("://", 1)[1]

    # Strip leading slash for relative paths like /uploads/...
    path = url.lstrip("/")

    # If this already looks like host/path (has a dot before first '/'), keep as-is
    host_part = path.split("/", 1)[0]
    if "." in host_part:
        return path

    # For plain uploads paths, prefix with CDN host and map them under
    # /images/, so we always store file.edusaint.in/images/<name>.
    if path.startswith("uploads/"):
        cdn_base = os.getenv("R2_CDN_BASE", "") or os.getenv("CDN_BASE", "")
        host = cdn_base.strip()
        if host:
            if "://" in host:
                host = host.split("://", 1)[1]
            basename = path.split("/")[-1]
            return f"{host}/images/{basename}"

    # Fallback: just return the relative path
    return path or url


def _process_concept_blocks_and_collect_urls(blocks):
    """Upload all base64 images in blocks to R2 and collect their URLs.

    Returns (updated_blocks, urls_for_card) where urls_for_card is a list of
    scheme-less URLs suitable for storing in Card.image_url as a JSON array.
    """
    if not isinstance(blocks, list):
        return blocks, []

    urls = []

    for block in blocks:
        if not isinstance(block, dict):
            continue
        b_type = block.get("type")
        if b_type not in ("image", "image-main"):
            continue
        img_val = block.get("image")
        if not isinstance(img_val, str) or not img_val:
            continue

        # If it's already a URL, just normalize and collect it.
        if not img_val.startswith("data:image"):
            norm = _normalize_url_for_storage(img_val)
            if norm:
                urls.append(norm)
            continue

        # Otherwise, upload the base64 image to R2.
        try:
            cdn_url = upload_base64_image_to_r2(img_val, folder="images")
        except Exception:
            current_app.logger.exception("Failed to upload concept image to R2")
            continue

        # Replace block image with the full CDN URL (for browser usage).
        block["image"] = cdn_url

        norm = _normalize_url_for_storage(cdn_url)
        if norm:
            urls.append(norm)

    return blocks, urls


def _collect_quiz_image_urls(data_json):
    """Collect all image URLs from quiz data_json.

    We don't upload anything here because quiz builder already uses /uploads
    to store media and returns URLs. We simply gather all relevant image URLs
    so they can be stored in Card.image_url as a JSON array.
    """
    if not isinstance(data_json, dict):
        return []

    questions = data_json.get("questions") or []
    if not isinstance(questions, list):
        return []

    urls = []

    for q in questions:
        if not isinstance(q, dict):
            continue

        # 1) Question-level image
        url = q.get("questionImageUrl")
        if isinstance(url, str) and url:
            norm = _normalize_url_for_storage(url)
            if norm:
                urls.append(norm)

        # 2) Option-level image URLs, if present
        options = q.get("options") or []
        if isinstance(options, list):
            for opt in options:
                if not isinstance(opt, dict):
                    continue
                ou = opt.get("imageUrl")
                if isinstance(ou, str) and ou:
                    norm = _normalize_url_for_storage(ou)
                    if norm:
                        urls.append(norm)

        # 3) Media object (include only if it's an image)
        media = q.get("media")
        if isinstance(media, dict):
            mu = media.get("url")
            mtype = media.get("type") or ""
            if isinstance(mu, str) and mu and (not mtype or str(mtype).startswith("image")):
                norm = _normalize_url_for_storage(mu)
                if norm:
                    urls.append(norm)

    # De-duplicate while preserving order
    seen = set()
    deduped = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        deduped.append(u)

    return deduped


def _extract_r2_keys_from_image_url(image_url_value):
    """Given Card.image_url value, return a list of R2 object keys to delete.

    image_url may be:
      - JSON array string of URLs (concept/quiz cards)
      - Single host/path string (other cards)

    We only consider URLs that ultimately map to our CDN host and have
    paths under /images/, and convert those to R2 keys like 'images/name.jpg'.
    """
    if not image_url_value:
        return []

    urls = []

    # Try to treat as JSON array first
    try:
        parsed = json.loads(image_url_value)
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, str) and item:
                    urls.append(item.strip())
        elif isinstance(parsed, str) and parsed:
            urls.append(parsed.strip())
    except Exception:
        # Fallback: assume it's a plain string
        if isinstance(image_url_value, str):
            urls.append(image_url_value.strip())

    keys = []
    if not urls:
        return keys

    # Determine our CDN host (scheme-less) for safety checks
    cdn_host = (os.getenv("R2_CDN_BASE", "") or CDN_BASE or "").strip()
    if cdn_host and "://" in cdn_host:
        cdn_host = cdn_host.split("://", 1)[1]

    for u in urls:
        if not u:
            continue
        # Strip any scheme
        if u.startswith("http://") or u.startswith("https://"):
            u_no_scheme = u.split("://", 1)[1]
        else:
            u_no_scheme = u

        # If it contains host/path, split; otherwise treat as already host/path
        parts = u_no_scheme.split("/", 1)
        if len(parts) == 2:
            host_part, path_part = parts[0], parts[1]
        else:
            host_part, path_part = "", parts[0]

        # Only try to delete if it matches our CDN host (when configured)
        if cdn_host and host_part and host_part != cdn_host:
            continue

        # We store images under images/<name>
        if path_part.startswith("images/"):
            keys.append(path_part)

    return keys


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
    claims = get_jwt()
    user_id = claims.get('sub')
    
    if not claims or claims.get('role') != 'admin':
        return {"success": False, "error": "Admin access required", "code": 403}, 403
    
    data = request.get_json(silent=True)
    if not data:
        return {"success": False, "error": "JSON payload required", "code": 400}, 400
    
    card_type = data.get('card_type', '').strip().lower()
    title = data.get('title', '').strip()
    # image_url for concept/quiz cards will be computed from their content as a
    # JSON array string of all image URLs. For other card types, still honor
    # an explicit image_url field if provided.
    image_url = (data.get('image_url') or '').strip() or None
    if image_url and card_type not in ['concept', 'quiz']:
        image_url = _normalize_url_for_storage(image_url) or None
    
    if card_type not in ['concept', 'quiz', 'video', 'interactive']:
        return {"success": False, "error": "Invalid card_type. Must be: concept, quiz, video, or interactive", "code": 400}, 400
    
    if not title:
        return {"success": False, "error": "Title is required", "code": 400}, 400
    
    topic_id = data.get('topic_id')
    lesson_id = data.get('lesson_id')
    
    if not topic_id and not lesson_id:
        return {"success": False, "error": "Either topic_id or lesson_id is required", "code": 400}, 400
    
    if topic_id:
        topic = Topic.query.get(topic_id)
        if not topic:
            return {"success": False, "error": "Topic not found", "code": 404}, 404
    
    if lesson_id:
        lesson = Lesson.query.get(lesson_id)
        if not lesson:
            return {"success": False, "error": "Lesson not found", "code": 404}, 404
    
    created_by_val = None
    if user_id and user_id != 'dev_admin':
        try:
            uid_int = int(user_id)
            if User.query.get(uid_int):
                created_by_val = uid_int
        except Exception:
            created_by_val = None

    try:
        data_json = data.get('data_json', {})
        if card_type == 'concept':
            # For concept cards, upload all base64 images and collect URLs.
            blocks = (data_json or {}).get('blocks') if isinstance(data_json, dict) else None
            if blocks:
                updated_blocks, urls = _process_concept_blocks_and_collect_urls(blocks)
                data_json['blocks'] = updated_blocks
                if urls:
                    # Store all URLs as JSON array string in image_url column
                    image_url = json.dumps(urls)
            data_json = compress_images_in_json(data_json)
        elif card_type == 'quiz':
            # For quiz cards, collect all image URLs from questions/options/media.
            quiz_urls = _collect_quiz_image_urls(data_json)
            if quiz_urls:
                image_url = json.dumps(quiz_urls)
            data_json = compress_images_in_json(data_json)

        new_card = Card(
            card_type=card_type,
            title=title,
            image_url=image_url,
            data_json=data_json,
            topic_id=topic_id,
            lesson_id=lesson_id,
            display_order=data.get('display_order', 0),
            created_by=created_by_val,
            published=True
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
                "image_url": new_card.image_url,
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
    is_authenticated = False
    try:
        verify_jwt_in_request(optional=True)
        claims = get_jwt() or {}
        is_authenticated = True if claims else False
    except Exception:
        is_authenticated = False

    query = Card.query

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

    if not is_authenticated:
        query = query.filter(Card.published.is_(True))
        if topic_id is None and lesson_id is None:
            return {
                "success": False,
                "error": "topic_id or lesson_id is required for public access",
                "code": 400
            }, 400

    query = query.order_by(Card.display_order, Card.created_at)

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
                "image_url": c.image_url,
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
    """Get a specific card by ID with parsed blocks.

    Publicly accessible: unauthenticated users may fetch only published cards.
    Authenticated users can fetch any card (subject to existence).
    """
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

    if not is_authenticated and not card.published:
        return {"success": False, "error": "Card is not published", "code": 403}, 403

    # Parse raw [[tags]] into structured blocks while keeping original data_json
    raw_data = card.data_json or {}
    parsed_blocks = parse_blocks(raw_data)

    return {
        "success": True,
        "card": {
            "id": card.id,
            "card_type": card.card_type,
            "title": card.title,
            "image_url": card.image_url,
            # For editor/web clients that expect the stored payload
            "data_json": raw_data,
            # For Dart/mobile or consumers that want parsed blocks
            "blocks": parsed_blocks,
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
        if 'title' in data:
            card.title = data['title']
        if 'data_json' in data:
            payload = data['data_json']
            if card.card_type == 'concept':
                # For concept updates, upload all base64 images and refresh URL list.
                blocks = (payload or {}).get('blocks') if isinstance(payload, dict) else None
                if blocks:
                    updated_blocks, urls = _process_concept_blocks_and_collect_urls(blocks)
                    payload['blocks'] = updated_blocks
                    if urls:
                        card.image_url = json.dumps(urls)
                payload = compress_images_in_json(payload)
            elif card.card_type == 'quiz':
                # For quiz updates, refresh all image URLs from questions/options/media.
                quiz_urls = _collect_quiz_image_urls(payload)
                if quiz_urls:
                    card.image_url = json.dumps(quiz_urls)
                payload = compress_images_in_json(payload)
            card.data_json = payload
        if 'image_url' in data:
            # Allow manual override only for non concept/quiz types; for
            # concept/quiz, image_url is derived from their content as JSON.
            if card.card_type not in ['concept', 'quiz']:
                iu = (data.get('image_url') or '').strip() or None
                iu = _normalize_url_for_storage(iu) or None
                card.image_url = iu
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
                "image_url": card.image_url,
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


@bp.route("/cards/<int:card_id>/update", methods=["POST"])
@jwt_required()
@limiter.limit("30/minute")
def update_card_via_post(card_id):
    """Update an existing card via POST for environments that block PUT."""
    return update_card(card_id)


@bp.route("/cards/<int:card_id>", methods=["DELETE"])
@jwt_required()
@limiter.limit("30/minute")
def delete_card(card_id):
    """Delete a card. Admin only."""
    claims = get_jwt()
    if not claims or claims.get('role') != 'admin':
        return {"success": False, "error": "Admin access required", "code": 403}, 403
    
    card = Card.query.get(card_id)
    if not card:
        return {"success": False, "error": "Card not found", "code": 404}, 404

    # Best-effort: remove any associated images from R2 before deleting the card
    if R2_BUCKET:
        try:
            keys = _extract_r2_keys_from_image_url(card.image_url)
            for key in keys:
                try:
                    s3.delete_object(Bucket=R2_BUCKET, Key=key)
                except Exception:
                    current_app.logger.exception("Failed to delete R2 object for card %s key=%s", card.id, key)
        except Exception:
            current_app.logger.exception("Failed to derive R2 keys for card %s", card.id)
    
    try:
        db.session.delete(card)
        db.session.commit()
        return {"success": True, "id": card_id}, 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to delete card')
        return {"success": False, "error": "Failed to delete card", "detail": str(e), "code": 500}, 500


@bp.route("/cards/<int:card_id>/delete", methods=["POST"])
@jwt_required()
@limiter.limit("30/minute")
def delete_card_via_post(card_id):
    """Delete a card using POST for environments that block DELETE."""
    return delete_card(card_id)


@bp.route("/topics/<int:topic_id>/cards", methods=["GET"])
def get_topic_cards(topic_id):
    """Get all cards for a specific topic."""
    topic = Topic.query.get(topic_id)
    if not topic:
        return {"success": False, "error": "Topic not found", "code": 404}, 404
    
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
                "image_url": card.image_url,
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
                "image_url": card.image_url,
                "display_order": card.display_order,
                "published": card.published,
                "created_at": card.created_at.isoformat() if card.created_at else None
            }
            for card in cards
        ]
    }, 200