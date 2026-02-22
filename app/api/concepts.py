from flask import request, jsonify
from app.extensions import db
from app.models import Card
from app.utils.image_utils import compress_images_in_json
from .text_parser import parse_blocks  # ✅ Added
from . import bp


@bp.route('/concepts/', methods=['GET'])
def get_concepts():
    """List all concept cards via the main API blueprint.

    Final URL: /api/v1/concepts/
    """
    concepts = Card.query.filter_by(card_type='concept').all()
    result = []
    for c in concepts:
        d = c.to_dict()
        d['blocks'] = parse_blocks(c.data_json or [])  # ✅ Parsed blocks added
        result.append(d)
    return jsonify(result)


@bp.route('/concepts/', methods=['POST'])
def save_concept():
    """Create a new concept card.

    Expects JSON: { "title": str, "blocks": [...] }
    """
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'success': False, 'error': 'title is required'}), 400

    blocks = data.get('blocks', [])
    blocks = compress_images_in_json(blocks)

    concept = Card(
        title=title,
        card_type='concept',
        data_json=blocks,
        published=False
    )
    db.session.add(concept)
    db.session.commit()

    # ✅ Return parsed blocks in response too
    d = concept.to_dict()
    d['blocks'] = parse_blocks(concept.data_json or [])

    return jsonify({'success': True, 'card': d}), 201