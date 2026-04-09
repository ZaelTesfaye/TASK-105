"""Content item service — articles, books, chapters, attachments."""
import hashlib
import json
import os
from datetime import datetime, timezone

import bleach

from flask import current_app
from app.extensions import db
from app.models.content import ContentItem, ContentVersion, Attachment
from app.models.user import User
from app.models.audit import AuditLog
from app.errors import NotFoundError, AppError
from flask import g

_ALLOWED_TAGS = [
    "p", "br", "strong", "em", "u", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "blockquote", "code", "pre", "a", "img",
]
_ALLOWED_ATTRS = {"a": ["href"], "img": ["src", "alt"]}

# Roles that may see draft (current_version) content; others see latest published only
_PRIVILEGED_CONTENT_ROLES = {"Administrator", "Operations Manager", "Moderator"}


def _sanitize(body: str) -> str:
    return bleach.clean(body, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)


def _cid() -> str:
    return getattr(g, "correlation_id", "n/a")


class ContentService:

    @staticmethod
    def _get_or_404(content_id: str) -> ContentItem:
        item = db.session.get(ContentItem, content_id)
        if item is None or item.deleted_at is not None:
            raise NotFoundError("content_item")
        return item

    @staticmethod
    def create(data: dict, author: User) -> dict:
        item = ContentItem(
            type=data["type"],
            parent_id=data.get("parent_id"),
            title=data["title"],
            status="draft",
            created_by=author.user_id,
        )
        db.session.add(item)
        db.session.flush()

        body = _sanitize(data.get("body", ""))
        version = ContentVersion(
            content_id=item.content_id,
            version=1,
            body=body,
            tags=json.dumps(data.get("tags", [])),
            categories=json.dumps(data.get("categories", [])),
            status="draft",
            created_by=author.user_id,
        )
        db.session.add(version)
        db.session.commit()
        result = item.to_dict()
        result.update(version.to_dict())
        return result

    @staticmethod
    def get(content_id: str, version: int | None = None, user=None) -> dict:
        item = ContentService._get_or_404(content_id)
        if version is not None:
            # Enforce the same privilege check for explicit version requests
            privileged = (
                user is not None
                and (
                    user.role in _PRIVILEGED_CONTENT_ROLES
                    or str(user.user_id) == str(item.created_by)
                )
            )
            v = ContentVersion.query.filter_by(content_id=content_id, version=version).first()
            # Non-privileged users may only see published versions
            if v is not None and not privileged and v.status != "published":
                raise NotFoundError("content_version")
        else:
            # Privileged roles (and the content creator) may read the draft head.
            # Everyone else receives only the latest published version.
            privileged = (
                user is not None
                and (
                    user.role in _PRIVILEGED_CONTENT_ROLES
                    or str(user.user_id) == str(item.created_by)
                )
            )
            if privileged:
                v = ContentVersion.query.filter_by(
                    content_id=content_id, version=item.current_version
                ).first()
            else:
                v = (
                    ContentVersion.query
                    .filter_by(content_id=content_id, status="published")
                    .order_by(ContentVersion.version.desc())
                    .first()
                )
        if v is None:
            raise NotFoundError("content_version")
        result = item.to_dict()
        result.update(v.to_dict())
        return result

    @staticmethod
    def update(content_id: str, data: dict, author: User) -> dict:
        item = ContentService._get_or_404(content_id)
        latest_v = ContentVersion.query.filter_by(content_id=content_id, version=item.current_version).first()

        new_version_num = item.current_version + 1
        body = _sanitize(data.get("body", latest_v.body if latest_v else ""))
        new_v = ContentVersion(
            content_id=item.content_id,
            version=new_version_num,
            body=body,
            tags=json.dumps(data.get("tags", json.loads(latest_v.tags) if latest_v else [])),
            categories=json.dumps(data.get("categories", json.loads(latest_v.categories) if latest_v else [])),
            status="draft",
            created_by=author.user_id,
        )
        if "title" in data:
            item.title = data["title"]
        item.current_version = new_version_num
        db.session.add(new_v)
        db.session.commit()
        result = item.to_dict()
        result.update(new_v.to_dict())
        return result

    @staticmethod
    def publish(content_id: str, actor: User) -> dict:
        item = ContentService._get_or_404(content_id)
        v = ContentVersion.query.filter_by(content_id=content_id, version=item.current_version).first()
        if v is None:
            raise NotFoundError("content_version")
        v.status = "published"
        v.published_at = datetime.now(timezone.utc)
        item.status = "published"
        db.session.add(AuditLog(
            action_type="content", actor_id=actor.user_id,
            target_type="content_item", target_id=str(content_id),
            after_state=json.dumps({"status": "published", "version": v.version}),
            correlation_id=_cid(),
        ))
        db.session.commit()
        result = item.to_dict()
        result.update(v.to_dict())
        return result

    @staticmethod
    def rollback(content_id: str, target_version: int, actor: User) -> dict:
        item = ContentService._get_or_404(content_id)
        v = ContentVersion.query.filter_by(content_id=content_id, version=target_version).first()
        if v is None:
            raise NotFoundError("content_version")
        item.current_version = target_version
        item.status = v.status
        db.session.add(AuditLog(
            action_type="content", actor_id=actor.user_id,
            target_type="content_item", target_id=str(content_id),
            after_state=json.dumps({"rollback_to_version": target_version}),
            correlation_id=_cid(),
        ))
        db.session.commit()
        result = item.to_dict()
        result.update(v.to_dict())
        return result

    @staticmethod
    def list_versions(content_id: str) -> list:
        ContentService._get_or_404(content_id)
        versions = ContentVersion.query.filter_by(content_id=content_id).order_by(ContentVersion.version.asc()).all()
        return [{"version": v.version, "status": v.status, "created_at": v.created_at.isoformat()} for v in versions]

    @staticmethod
    def add_attachment(content_id: str, file, actor: User) -> Attachment:
        ContentService._get_or_404(content_id)
        if file is None:
            raise AppError("file_required", "No file provided", status_code=400)

        max_bytes = current_app.config["ATTACHMENT_MAX_BYTES"]
        allowed_mime = current_app.config["ATTACHMENT_ALLOWED_MIME"]
        attach_dir = current_app.config["ATTACHMENT_DIR"]

        data = file.read()
        if len(data) > max_bytes:
            raise AppError("file_too_large", "File exceeds 25 MB limit", status_code=413)

        mime = file.mimetype or "application/octet-stream"
        if mime not in allowed_mime:
            raise AppError("unsupported_media_type", f"Allowed types: {', '.join(allowed_mime)}", status_code=415)

        sha256 = hashlib.sha256(data).hexdigest()
        filename = f"{sha256}_{file.filename}"
        local_path = os.path.join(attach_dir, filename)
        os.makedirs(attach_dir, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(data)

        attachment = Attachment(
            content_id=content_id,
            filename=file.filename,
            mime_type=mime,
            size_bytes=len(data),
            sha256=sha256,
            local_path=local_path,
            created_by=actor.user_id,
        )
        db.session.add(attachment)
        db.session.commit()
        return attachment

    @staticmethod
    def list_attachments(content_id: str) -> list:
        ContentService._get_or_404(content_id)
        attachments = Attachment.query.filter_by(content_id=content_id, deleted_at=None).all()
        return [a.to_dict() for a in attachments]

    @staticmethod
    def delete_attachment(content_id: str, attachment_id: str) -> None:
        att = db.session.get(Attachment, attachment_id)
        if att is None or str(att.content_id) != content_id:
            raise NotFoundError("attachment")
        att.deleted_at = datetime.now(timezone.utc)
        db.session.commit()
