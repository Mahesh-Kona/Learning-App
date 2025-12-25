from flask import request, jsonify
from app.extensions import db
from app.models import Card
from . import bp


@bp.route('/concepts/', methods=['GET'])
def get_concepts():
    """List all concept cards via the main API blueprint.

    Final URL: /api/v1/concepts/
    """
    concepts = Card.query.filter_by(card_type='concept').all()
    return jsonify([c.to_dict() for c in concepts])


@bp.route('/concepts/', methods=['POST'])
def save_concept():
    """Create a new concept card.

    Expects JSON: { "title": str, "blocks": [...] }
    """
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'success': False, 'error': 'title is required'}), 400

    concept = Card(
        title=title,
        card_type='concept',
        data_json=data.get('blocks', []),
        published=False
    )
    db.session.add(concept)
    db.session.commit()
    return jsonify({'success': True, 'card': concept.to_dict()}), 201
