import os
from flask import Blueprint, request, current_app
from werkzeug.utils import secure_filename
from ..models import Asset
from ..extensions import db, limiter
ALLOWED = {"png", "jpg", "jpeg", "gif", "webp", "mp4", "pdf"}

from . import bp


def allowed_file(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in ALLOWED


def _save_local(fileobj, upload_path, filename):
    os.makedirs(upload_path, exist_ok=True)
    filepath = os.path.join(upload_path, filename)
    fileobj.save(filepath)
    return filepath


def _upload_s3(fileobj, bucket, key, extra_args=None):
    # Lazy import boto3 so it's optional
    try:
        import boto3
    except Exception:
        raise RuntimeError("boto3 is required for S3 uploads")
    s3 = boto3.client(
        's3',
        aws_access_key_id=current_app.config.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=current_app.config.get('AWS_SECRET_ACCESS_KEY'),
        region_name=current_app.config.get('AWS_REGION')
    )
    extra_args = extra_args or {}
    # fileobj may be a FileStorage; seek to start
    fileobj.stream.seek(0)
    s3.upload_fileobj(fileobj.stream, bucket, key, ExtraArgs=extra_args)
    # return public URL (assuming bucket policy/public or presigned URL used)
    return f"https://{bucket}.s3.amazonaws.com/{key}"


@bp.route("/uploads", methods=["POST"])
@limiter.limit("10/minute")
def upload():
    # Basic request size check (Flask may also enforce MAX_CONTENT_LENGTH globally)
    max_len = current_app.config.get('MAX_CONTENT_LENGTH')
    if max_len and request.content_length and request.content_length > max_len:
        return {"success": False, "error": "request too large", "code": 413}, 413

    if "file" not in request.files:
        return {"success": False, "error": "no file part", "code": 400}, 400
    f = request.files["file"]
    if f.filename == "":
        return {"success": False, "error": "no selected file", "code": 400}, 400
    if not allowed_file(f.filename):
        return {"success": False, "error": "file type not allowed", "code": 400}, 400

    filename = secure_filename(f.filename)
    upload_to_s3 = bool(current_app.config.get('S3_BUCKET'))

    if upload_to_s3:
        key = f"uploads/{filename}"
        try:
            # attempt to determine size before upload
            size = None
            try:
                # try request content length first
                size = int(request.content_length) if request.content_length else None
            except Exception:
                size = None
            try:
                # try to get filesize by seeking stream (works for small uploads)
                pos = None
                if hasattr(f, 'stream') and hasattr(f.stream, 'seek'):
                    try:
                        pos = f.stream.tell()
                    except Exception:
                        pos = None
                    try:
                        f.stream.seek(0, os.SEEK_END)
                        size = f.stream.tell()
                        # rewind
                        if pos is not None:
                            f.stream.seek(pos)
                        else:
                            f.stream.seek(0)
                    except Exception:
                        pass
            except Exception:
                pass
            url = _upload_s3(f, current_app.config['S3_BUCKET'], key, extra_args={'ACL': 'public-read', 'ContentType': f.mimetype})
            mime_type = f.mimetype
        except Exception as e:
            current_app.logger.exception("S3 upload failed")
            return {"success": False, "error": "upload failed", "code": 500}, 500
    else:
        UP = current_app.config.get("UPLOAD_PATH", "/tmp/uploads")
        # Store videos under a dedicated subfolder for organization
        subfolder = "videos" if (f.mimetype or "").startswith("video/") else ""
        upload_path = os.path.join(UP, subfolder) if subfolder else UP
        filepath = _save_local(f, upload_path, filename)
        size = os.path.getsize(filepath)
        # Validate saved size against configured limit
        if max_len and size and size > max_len:
            try:
                os.remove(filepath)
            except Exception:
                current_app.logger.exception("failed to remove oversize file")
            return {"success": False, "error": "file too large", "code": 413}, 413
        mime_type = f.mimetype
        url = f"/uploads/{(subfolder + '/' if subfolder else '')}{filename}"

    # uploader id - try to get from JWT if present (optional)
    uploader_id = None
    try:
        from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
        verify_jwt_in_request(optional=True)
        ident = get_jwt_identity()
        current_app.logger.debug('upload: raw jwt identity: %s', repr(ident))
        if isinstance(ident, dict):
            uploader_id = ident.get("id")
        elif isinstance(ident, (str, int)) and ident:
            try:
                uploader_id = int(ident)
            except Exception:
                uploader_id = None
        else:
            uploader_id = None
        current_app.logger.debug('upload: resolved uploader_id: %s', repr(uploader_id))
    except Exception:
        uploader_id = None

    asset_created = False
    db_error = None
    try:
        # Always record the upload in the assets table. uploader_id may be None for anonymous uploads.
        asset = Asset(url=url, uploader_id=uploader_id, size=size, mime_type=mime_type)
        db.session.add(asset)
        db.session.commit()
        asset_created = True
        # Log success with created asset id for easier debugging
        try:
            current_app.logger.info('Asset created id=%s uploader_id=%s url=%s size=%s', getattr(asset, 'id', None), uploader_id, url, size)
        except Exception:
            # Ensure logging does not break the response
            current_app.logger.debug('Asset created (logging failed) uploader_id=%s url=%s', uploader_id, url)
    except Exception as e:
        # Rollback the session to keep it clean
        try:
            db.session.rollback()
        except Exception:
            current_app.logger.exception('rollback failed')

        # Log the full exception for debugging
        current_app.logger.exception('Failed to create Asset row: %s', e)
        db_error = str(e)

        # Fallback attempt: try to insert without uploader_id column using a raw SQL INSERT (works if DB schema allows NULL or has default)
        try:
            from sqlalchemy import text
            engine = db.get_engine(current_app)
            # Use DB-level NOW()/CURRENT_TIMESTAMP depending on dialect; use literal SQL NOW() which works for MySQL
            sql = text('INSERT INTO assets (url, size, mime_type, created_at) VALUES (:url, :size, :mime_type, NOW())')
            # use a transactional begin() so the insert is committed
            with engine.begin() as conn:
                conn.execute(sql, { 'url': url, 'size': size, 'mime_type': mime_type })
            asset_created = True
            current_app.logger.info('Asset created via fallback raw INSERT url=%s size=%s', url, size)
        except Exception as e2:
            # fallback also failed; capture that message
            current_app.logger.exception('Fallback asset insert failed: %s', e2)
            try:
                db_error = (db_error or '') + ' | fallback: ' + str(e2)
            except Exception:
                db_error = db_error or str(e2)

    # include asset id when available so callers can reference the created Asset row
    resp = {"success": True, "url": url, "size": size, "mime_type": mime_type, "asset_created": asset_created}
    try:
        if asset_created and hasattr(asset, 'id') and asset.id:
            resp['asset_id'] = asset.id
    except Exception:
        # ignore if asset id not available
        pass
    if db_error:
        resp['db_error'] = db_error
    return resp


@bp.route('/uploads/presign', methods=['POST'])
def presign():
    """Return a presigned upload URL for S3. Requires S3 enabled."""
    if not current_app.config.get('S3_BUCKET'):
        return {"success": False, "error": "S3 not configured", "code": 400}, 400
    data = request.get_json() or {}
    filename = data.get('filename')
    content_type = data.get('content_type', 'application/octet-stream')
    if not filename:
        return {"success": False, "error": "filename required", "code": 400}, 400
    try:
        import boto3
        s3 = boto3.client(
            's3',
            aws_access_key_id=current_app.config.get('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=current_app.config.get('AWS_SECRET_ACCESS_KEY'),
            region_name=current_app.config.get('AWS_REGION')
        )
        key = f"uploads/{secure_filename(filename)}"
        presigned = s3.generate_presigned_post(
            Bucket=current_app.config['S3_BUCKET'],
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[["starts-with", "$Content-Type", ""]],
            ExpiresIn=3600
        )
        return {"success": True, "data": presigned}
    except Exception as e:
        current_app.logger.exception("presign failed")
        return {"success": False, "error": "presign failed", "code": 500}, 500


@bp.route('/debug/assets', methods=['GET'])
def debug_assets():
    """Dev helper: return the most recent assets.
    Only enabled when DEBUG or ALLOW_DEBUG_ROUTES is truthy in config.
    """
    if not (current_app.config.get('DEBUG') or current_app.config.get('ALLOW_DEBUG_ROUTES')):
        return {"success": False, "error": "not found", "code": 404}, 404
    try:
        limit = int(request.args.get('limit', 10))
    except Exception:
        limit = 10
    items = Asset.query.order_by(Asset.created_at.desc()).limit(limit).all()
    data = []
    for a in items:
        data.append({
            'id': a.id,
            'url': a.url,
            'uploader_id': a.uploader_id,
            'size': a.size,
            'mime_type': a.mime_type,
            'created_at': a.created_at.isoformat() if getattr(a, 'created_at', None) else None,
        })
    return {"success": True, "data": data}
