"""Data migration: convert base64 images in existing cards to R2 CDN URLs.

This script scans all existing `cards` rows of type `concept` and `quiz` and
applies the same logic used by the API when creating/updating cards:

- For concept cards, it uploads any base64 `blocks[*].image` values to
  Cloudflare R2 and updates `data_json.blocks` and `image_url` accordingly.
- For quiz cards, it uploads any base64 images found in questionImageUrl,
  options[*].imageUrl, or media.url, and updates `data_json` and `image_url`.

Run from the project root (where app/ and scripts/ live):

    python scripts/migrate_card_images_to_r2.py

You can also do a dry run without committing changes:

    python scripts/migrate_card_images_to_r2.py --dry-run
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List

from flask import current_app

# Ensure project root (which contains the `app` package) is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from app.extensions import db
from app.models import Card
from app.utils.image_utils import compress_images_in_json
from app.api.cards import _compute_image_folder, _normalize_url_for_storage
from utils.upload import upload_base64_image_to_r2
# Load .env via the same mechanism as the main app so that R2_* vars
# are available before we import r2_client.
from app.config import env_path, load_dotenv

load_dotenv(env_path, override=True)

from r2_client import R2_BUCKET, CDN_BASE


def _rewrite_base64_images_in_payload(
    payload: Dict[str, Any],
    image_folder: str,
    card_id: int,
) -> tuple[Dict[str, Any], List[str]]:
    """Walk the entire payload and replace any base64 image strings with CDN URLs.

    This is schema-agnostic: any string starting with "data:image" anywhere in
    the JSON will be uploaded to R2 and replaced with the resulting CDN URL.
    Returns (updated_payload, list_of_normalized_urls_for_image_url_column).
    """

    upload_errors: List[str] = []
    urls: List[str] = []
    counter = 0

    def _walk(value: Any) -> Any:
        nonlocal counter

        if isinstance(value, dict):
            return {k: _walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_walk(v) for v in value]

        if isinstance(value, str) and value.startswith("data:image"):
            counter += 1
            filename_base = str(card_id) or "card"
            filename = f"{filename_base}-{counter}"
            try:
                cdn_url = upload_base64_image_to_r2(
                    value,
                    folder=image_folder,
                    filename=filename,
                )
            except Exception as exc:
                current_app.logger.exception("Failed to upload image to R2 during migration")
                upload_errors.append(f"Failed to upload image #{counter} for card {card_id}: {exc}")
                return value

            norm = _normalize_url_for_storage(cdn_url)
            if norm:
                urls.append(norm)
            return cdn_url

        return value

    updated = _walk(payload)

    # De-duplicate URLs while preserving order
    seen: set[str] = set()
    deduped_urls: List[str] = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        deduped_urls.append(u)

    if upload_errors:
        raise ValueError(
            "; ".join(
                [
                    "Some images could not be stored in Cloudflare R2 during migration. "
                    "Please check your R2 configuration (R2_ACCOUNT_ID, R2_ACCESS_KEY, "
                    "R2_SECRET_KEY, R2_BUCKET, R2_CDN_BASE) and try again.",
                ]
            )
        )

    return updated, deduped_urls


def migrate_cards(dry_run: bool = False) -> None:
    """Perform the data migration for concept and quiz cards."""

    app = create_app()

    with app.app_context():
        logger = current_app.logger

        # Validate R2 configuration up front. If this fails, we abort the
        # migration rather than partially processing cards.
        bucket = (R2_BUCKET or "").strip() if isinstance(R2_BUCKET, str) else ""
        cdn_base = (CDN_BASE or "").strip() if isinstance(CDN_BASE, str) else ""
        if not bucket:
            raise RuntimeError(
                "R2_BUCKET is not configured or empty. Cannot migrate base64 images to CDN."
            )
        if not cdn_base:
            raise RuntimeError(
                "R2_CDN_BASE is not configured or empty. Cannot migrate base64 images to CDN."
            )

        concept_count = 0
        quiz_count = 0
        skipped_no_base64 = 0

        # Only consider concept and quiz cards
        cards: List[Card] = (
            Card.query.filter(Card.card_type.in_(["concept", "quiz"]))
            .order_by(Card.id)
            .all()
        )

        logger.info("Starting card image migration: %d cards to inspect", len(cards))

        for card in cards:
            payload: Any = card.data_json or {}
            if not isinstance(payload, dict):
                skipped_no_base64 += 1
                continue

            try:
                try:
                    image_folder = _compute_image_folder(
                        topic_id=card.topic_id,
                        lesson_id=card.lesson_id,
                    )
                except Exception:
                    image_folder = "images"

                updated_payload, urls = _rewrite_base64_images_in_payload(
                    payload,
                    image_folder=image_folder,
                    card_id=card.id,
                )

                if not urls:
                    skipped_no_base64 += 1
                    continue

                # Store all normalized URLs as JSON array string in image_url column
                card.image_url = json.dumps(urls)

                # Compress any remaining base64 blobs in the payload (defensive)
                updated_payload = compress_images_in_json(updated_payload)
                card.data_json = updated_payload

                if card.card_type == "concept":
                    concept_count += 1
                elif card.card_type == "quiz":
                    quiz_count += 1

            except ValueError as e:
                # Typically raised when R2 upload fails. For this migration,
                # we treat any such error as fatal so that a successful run
                # guarantees all base64 images have been converted.
                logger.error(
                    "Aborting migration due to image migration error on card %s: %s",
                    card.id,
                    e,
                )
                db.session.rollback()
                raise
            except Exception as e:  # pragma: no cover - defensive
                logger.exception("Unexpected error while migrating card %s: %s", card.id, e)
                db.session.rollback()
                continue

        if dry_run:
            db.session.rollback()
            logger.info(
                "Dry run complete. Concept cards migrated: %d, quiz cards migrated: %d, "
                "skipped (no base64 or invalid payload): %d",
                concept_count,
                quiz_count,
                skipped_no_base64,
            )
        else:
            db.session.commit()
            logger.info(
                "Migration complete. Concept cards migrated: %d, quiz cards migrated: %d, "
                "skipped (no base64 or invalid payload): %d",
                concept_count,
                quiz_count,
                skipped_no_base64,
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate existing concept/quiz cards: upload base64 images to R2 and store CDN URLs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without committing changes to the database.",
    )
    args = parser.parse_args()

    migrate_cards(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
