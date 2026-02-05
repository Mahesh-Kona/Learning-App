import os
import re
import json

from flask import request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt

from ..extensions import limiter
from . import bp


# ---------------- HELPERS ----------------

_blank_pattern = re.compile(r"\[\[(.*?)\]\]")


def extract_blanks(text: str):
    """Extract blanks from authoring text in the form [[answer]]."""
    if not text:
        return []
    return _blank_pattern.findall(text)


def get_payload():
    """Return JSON or form payload for requests that may send either."""
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form or {}


def _get_upload_folder() -> str:
    """Resolve upload folder for activity media.

    Prefer a specific FIB/activities upload path when configured, otherwise
    fall back to the general UPLOAD_PATH, and finally to a local 'uploads'
    directory under the application root.
    """
    cfg = current_app.config
    folder = cfg.get("FIB_UPLOAD_PATH") or cfg.get("UPLOAD_PATH") or "uploads"
    if not os.path.isabs(folder):
        folder = os.path.join(current_app.root_path, folder)
    os.makedirs(folder, exist_ok=True)
    return folder


def _require_admin() -> bool:
    """Return True if the current JWT belongs to an admin user."""
    claims = get_jwt() or {}
    return bool(claims and claims.get("role") == "admin")


# ---------------- ROUTES ----------------


def _get_activity_storage_path() -> str:
    """Return path to JSON file used to store the single activity."""
    base = os.path.join(current_app.instance_path, "dynamic_json")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "fib_activity.json")


@bp.route("/activity/save", methods=["POST"])
@jwt_required()
@limiter.limit("30/minute")
def save_activity():
    """Create or update the single fill-in-the-blanks activity.

    Instead of relying on a dedicated DB table, this persists the
    latest activity to a JSON file under instance/dynamic_json so it
    works without additional migrations.
    """
    if not _require_admin():
        return {"success": False, "error": "Admin access required", "code": 403}, 403

    data = get_payload()
    file = request.files.get("media")

    content = data.get("content", "") or ""
    blanks = extract_blanks(content)

    media_filename = None
    if file and file.filename:
        upload_folder = _get_upload_folder()
        path = os.path.join(upload_folder, file.filename)
        file.save(path)
        media_filename = file.filename

    activity_payload = {
        "title": (data.get("title") or "").strip(),
        "activity_type": (data.get("activity_type") or "").strip(),
        "instructions": data.get("instructions") or "",
        "content": content,
        "blanks": blanks,
        "media": media_filename,
    }

    storage_path = _get_activity_storage_path()
    try:
        with open(storage_path, "w", encoding="utf-8") as f:
            json.dump(activity_payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        current_app.logger.exception("Failed to save activity JSON")
        return {
            "success": False,
            "error": "Failed to save activity",
            "detail": str(e),
            "code": 500,
        }, 500

    return jsonify({"success": True, "blanks": blanks})


@bp.route("/activity/load", methods=["GET"])
@jwt_required(optional=True)
@limiter.limit("60/minute")
def load_activity():
    """Load the single stored activity, if any."""
    storage_path = _get_activity_storage_path()
    if not os.path.exists(storage_path):
        return jsonify({"success": False}), 200

    try:
        with open(storage_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        current_app.logger.exception("Failed to load activity JSON")
        return jsonify({"success": False, "error": "Failed to load activity"}), 500

    return jsonify({"success": True, **payload})


@bp.route("/activity/preview", methods=["POST"])
@limiter.limit("60/minute")
def preview_activity():
    """Preview a fill-in-the-blanks text without persisting it.

    Expects "content" in JSON/form payload with [[answer]] markers.
    Returns the preview text (with blanks replaced by "_____") and
    the list of extracted blanks.
    """
    data = get_payload()
    content = data.get("content", "") or ""

    blanks = extract_blanks(content)
    # Replace [[...]] with plain underline placeholders for preview
    preview = _blank_pattern.sub("_____", content)

    return jsonify({"success": True, "preview": preview, "blanks": blanks})


@bp.route("/activity/delete", methods=["DELETE"])
@jwt_required()
@limiter.limit("30/minute")
def delete_activity():
    """Delete the stored activity, if any."""
    if not _require_admin():
        return {"success": False, "error": "Admin access required", "code": 403}, 403

    storage_path = _get_activity_storage_path()
    try:
        if os.path.exists(storage_path):
            os.remove(storage_path)
    except Exception as e:
        current_app.logger.exception("Failed to delete activity JSON")
        return {
            "success": False,
            "error": "Failed to delete activity",
            "detail": str(e),
            "code": 500,
        }, 500

    return jsonify({"success": True})


@bp.route("/activity/export", methods=["GET"])
@jwt_required()
@limiter.limit("30/minute")
def export_activity():
    """Export the stored activity as a simple JSON payload."""
    if not _require_admin():
        return {"success": False, "error": "Admin access required", "code": 403}, 403

    storage_path = _get_activity_storage_path()
    if not os.path.exists(storage_path):
        return jsonify({"success": False, "error": "No activity found"}), 404

    try:
        with open(storage_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        current_app.logger.exception("Failed to export activity JSON")
        return jsonify({"success": False, "error": "Failed to export activity"}), 500

    return jsonify({
        "success": True,
        "title": payload.get("title"),
        "type": payload.get("activity_type"),
        "instructions": payload.get("instructions"),
        "content": payload.get("content"),
        "answers": payload.get("blanks", []),
        "media": payload.get("media"),
    })
