"""
Daily 03:00 UTC:
1. Delete files on disk where Attachment.deleted_at IS NOT NULL.
2. Remove orphaned files in the attachments directory not referenced by any row.
"""
import json
import logging
import os

from flask import current_app, g

from app.extensions import db
from app.models.content import Attachment

logger = logging.getLogger(__name__)


def cleanup_attachments() -> None:
    cid = getattr(g, "correlation_id", "")
    attach_dir = current_app.config.get("ATTACHMENT_DIR", "data/attachments")

    # 1. Remove soft-deleted attachment files
    deleted = Attachment.query.filter(Attachment.deleted_at.isnot(None)).all()
    for att in deleted:
        if att.local_path and os.path.exists(att.local_path):
            try:
                os.remove(att.local_path)
                logger.info(json.dumps({"event": "attachment_deleted", "path": att.local_path, "correlation_id": cid}))
            except OSError as e:
                logger.warning(json.dumps({"event": "attachment_delete_error", "path": att.local_path, "error": str(e), "correlation_id": cid}))
        db.session.delete(att)

    db.session.commit()

    # 2. Remove orphaned files (on disk but not in DB)
    active_paths = {a.local_path for a in Attachment.query.filter(Attachment.deleted_at.is_(None)).all()}
    if not os.path.isdir(attach_dir):
        return
    for filename in os.listdir(attach_dir):
        full_path = os.path.join(attach_dir, filename)
        if full_path not in active_paths:
            try:
                os.remove(full_path)
                logger.info(json.dumps({"event": "orphan_attachment_removed", "path": full_path, "correlation_id": cid}))
            except OSError as e:
                logger.warning(json.dumps({"event": "orphan_remove_error", "path": full_path, "error": str(e), "correlation_id": cid}))
