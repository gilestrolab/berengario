"""
Admin routes for the teach-attempt moderation queue.

When a registered tenant user with role=querier emails the teach address,
their submission is queued in PendingTeachSubmission instead of being
silently dropped (see src/email/email_processor.py:_queue_for_moderation).
This router lets admins review, approve (with optional promotion to teacher),
or reject those submissions.
"""

import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.routes.helpers import resolve_component
from src.config import settings as app_settings

logger = logging.getLogger(__name__)


class ApproveRequest(BaseModel):
    promote_to_teacher: bool = True
    notes: Optional[str] = None


class RejectRequest(BaseModel):
    notes: Optional[str] = None


def create_moderation_router(
    platform_db_manager,
    require_admin,
    component_resolver=None,
    storage_backend=None,
    email_sender=None,
    kb_manager=None,
    document_processor=None,
):
    """
    Create the moderation router.

    Args:
        platform_db_manager: TenantDBManager for platform DB access.
        require_admin: Admin authentication dependency.
        component_resolver: ComponentResolver for tenant components.
        storage_backend: StorageBackend instance (None=ST/local mode).
        email_sender: EmailSender instance.
        kb_manager: Default KnowledgeBaseManager (used when no resolver).
        document_processor: Default DocumentProcessor (used when no resolver).

    Returns:
        Configured APIRouter.
    """
    router = APIRouter(prefix="/api/admin/moderation", tags=["moderation"])

    def _get_kb(session):
        return resolve_component(component_resolver, session, "kb_manager", kb_manager)

    def _get_dp(session):
        return resolve_component(
            component_resolver, session, "doc_processor", document_processor
        )

    def _get_tenant_db(session):
        if component_resolver:
            components = component_resolver.resolve(session)
            return components.conversation_manager.db_manager
        from src.email.db_manager import db_manager as default_db_manager

        return default_db_manager

    def _get_tenant_kb_documents_path(session):
        if component_resolver and session.tenant_slug:
            components = component_resolver.resolve(session)
            return components.context.kb_documents_path
        return app_settings.kb_documents_path

    def _get_tenant_instance_name(session):
        if component_resolver and session.tenant_slug:
            components = component_resolver.resolve(session)
            return components.context.instance_name
        return app_settings.instance_name

    def _local_moderation_path(submission_id: str) -> Path:
        return Path("data/moderation") / submission_id

    def _read_attachment(tenant_slug: Optional[str], record: dict) -> bytes:
        key = record["key"]
        if storage_backend and tenant_slug:
            return storage_backend.get(tenant_slug, key)
        local = _local_moderation_path(record["key"].split("/", 1)[1].split("/", 1)[0])
        # local key looks like "moderation/<id>/<filename>"; fall back to key parts
        parts = key.split("/")
        if len(parts) >= 3:
            local = Path("data/moderation") / parts[1] / parts[2]
        return local.read_bytes()

    def _delete_attachment(tenant_slug: Optional[str], record: dict) -> None:
        key = record["key"]
        if storage_backend and tenant_slug:
            try:
                storage_backend.delete(tenant_slug, key)
            except Exception as e:
                logger.warning("Failed to delete attachment %s: %s", key, e)
            return
        parts = key.split("/")
        if len(parts) >= 3:
            local = Path("data/moderation") / parts[1] / parts[2]
            try:
                local.unlink(missing_ok=True)
                if local.parent.exists() and not any(local.parent.iterdir()):
                    local.parent.rmdir()
            except Exception as e:
                logger.warning("Failed to delete local attachment %s: %s", local, e)

    def _archive_to_kb(
        tenant_slug: Optional[str],
        documents_dir: Path,
        filename: str,
        data: bytes,
    ) -> Path:
        if storage_backend and tenant_slug:
            storage_backend.put(
                tenant_slug,
                f"kb/documents/{filename}",
                data,
            )
            return documents_dir / filename
        documents_dir.mkdir(parents=True, exist_ok=True)
        dest = documents_dir / filename
        if dest.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            stem, dot, ext = filename.rpartition(".")
            if dot:
                filename = f"{stem}_{timestamp}.{ext}"
            else:
                filename = f"{filename}_{timestamp}"
            dest = documents_dir / filename
        dest.write_bytes(data)
        return dest

    def _send_decision_email(
        instance_name: str,
        to_address: str,
        decision: str,
        notes: Optional[str],
    ) -> None:
        if email_sender is None:
            return
        try:
            if decision == "approved":
                subject = f"[{instance_name}] Your submission has been approved"
                body_text = (
                    f"Good news — your recent submission to {instance_name} "
                    "has been approved and added to the knowledge base.\n\n"
                )
                body_html = (
                    f"<p>Good news — your recent submission to "
                    f"<strong>{instance_name}</strong> has been approved and "
                    "added to the knowledge base.</p>"
                )
            else:
                subject = f"[{instance_name}] Your submission was not added"
                body_text = (
                    f"Thank you for your submission to {instance_name}. After "
                    "review, the material was not added to the knowledge "
                    "base.\n\n"
                )
                body_html = (
                    f"<p>Thank you for your submission to "
                    f"<strong>{instance_name}</strong>. After review, the "
                    "material was not added to the knowledge base.</p>"
                )
            if notes:
                body_text += f"Notes from the administrator:\n{notes}\n\n"
                body_html += (
                    "<p><strong>Notes from the administrator:</strong><br>"
                    f"{notes}</p>"
                )
            body_text += f"---\n{instance_name}"
            body_html += f"<hr><p><em>{instance_name}</em></p>"
            email_sender.send_reply(
                to_address=to_address,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
            )
        except Exception as e:
            logger.error("Failed to send moderation decision email: %s", e)

    @router.get("/queue/pending-count")
    def pending_count(session=Depends(require_admin)):
        from src.email.db_models import (
            PendingSubmissionStatus,
            PendingTeachSubmission,
        )

        tenant_db = _get_tenant_db(session)
        with tenant_db.get_session() as db_session:
            count = (
                db_session.query(PendingTeachSubmission)
                .filter(
                    PendingTeachSubmission.status == PendingSubmissionStatus.PENDING
                )
                .count()
            )
        return {"count": count}

    @router.get("/queue")
    def list_queue(
        status: str = "pending",
        session=Depends(require_admin),
    ):
        from src.email.db_models import (
            PendingSubmissionStatus,
            PendingTeachSubmission,
        )

        tenant_db = _get_tenant_db(session)
        with tenant_db.get_session() as db_session:
            q = db_session.query(PendingTeachSubmission)
            if status != "all":
                try:
                    enum_value = PendingSubmissionStatus(status.lower())
                except ValueError:
                    raise HTTPException(
                        status_code=400, detail=f"Invalid status: {status}"
                    )
                q = q.filter(PendingTeachSubmission.status == enum_value)
            rows = q.order_by(PendingTeachSubmission.created_at.desc()).limit(200).all()
            return {"submissions": [r.to_dict() for r in rows]}

    @router.get("/{submission_id}")
    def get_submission(submission_id: str, session=Depends(require_admin)):
        from src.email.db_models import PendingTeachSubmission

        tenant_db = _get_tenant_db(session)
        with tenant_db.get_session() as db_session:
            row = (
                db_session.query(PendingTeachSubmission)
                .filter(PendingTeachSubmission.id == submission_id)
                .first()
            )
            if row is None:
                raise HTTPException(status_code=404, detail="Submission not found")
            return row.to_dict()

    @router.get("/{submission_id}/attachments/{filename}")
    def download_attachment(
        submission_id: str,
        filename: str,
        session=Depends(require_admin),
    ):
        from src.email.db_models import PendingTeachSubmission

        tenant_db = _get_tenant_db(session)
        with tenant_db.get_session() as db_session:
            row = (
                db_session.query(PendingTeachSubmission)
                .filter(PendingTeachSubmission.id == submission_id)
                .first()
            )
            if row is None:
                raise HTTPException(status_code=404, detail="Submission not found")
            record = next(
                (a for a in (row.attachment_keys or []) if a["filename"] == filename),
                None,
            )
            if record is None:
                raise HTTPException(status_code=404, detail="Attachment not found")
            data = _read_attachment(session.tenant_slug, record)

        from io import BytesIO

        return StreamingResponse(
            BytesIO(data),
            media_type=record.get("mime_type") or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.post("/{submission_id}/approve")
    def approve_submission(
        submission_id: str,
        request: ApproveRequest,
        session=Depends(require_admin),
    ):
        from src.email.db_models import (
            PendingSubmissionStatus,
            PendingTeachSubmission,
        )

        tenant_db = _get_tenant_db(session)
        with tenant_db.get_session() as db_session:
            row = (
                db_session.query(PendingTeachSubmission)
                .filter(PendingTeachSubmission.id == submission_id)
                .first()
            )
            if row is None:
                raise HTTPException(status_code=404, detail="Submission not found")
            if row.status != PendingSubmissionStatus.PENDING:
                raise HTTPException(
                    status_code=409,
                    detail=f"Submission already {row.status.value}",
                )
            data = row.to_dict()

        documents_dir = _get_tenant_kb_documents_path(session)
        kb = _get_kb(session)
        dp = _get_dp(session)
        chunks_total = 0
        archived_files: list = []

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for record in data["attachment_keys"] or []:
                try:
                    raw = _read_attachment(session.tenant_slug, record)
                except Exception as e:
                    logger.error(
                        "Could not read attachment %s for approval: %s",
                        record.get("filename"),
                        e,
                    )
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to load attachment {record.get('filename')}",
                    )

                temp_file = tmp_path / record["filename"]
                temp_file.write_bytes(raw)

                nodes = dp.process_document(
                    file_path=temp_file,
                    source_type="moderation_approved",
                    extra_metadata={
                        "filename": record["filename"],
                        "submitted_by": data["submitter_email"],
                        "approved_by": session.email,
                        "submission_id": submission_id,
                    },
                )
                if nodes:
                    kb.add_nodes(nodes)
                    chunks_total += len(nodes)
                permanent = _archive_to_kb(
                    session.tenant_slug,
                    documents_dir,
                    record["filename"],
                    raw,
                )
                archived_files.append(str(permanent))

        promoted = False
        if request.promote_to_teacher and session.tenant_id:
            from src.platform.models import TenantUser, TenantUserRole

            with platform_db_manager.get_platform_session() as ps:
                user = (
                    ps.query(TenantUser)
                    .filter(
                        TenantUser.email == data["submitter_email"],
                        TenantUser.tenant_id == session.tenant_id,
                    )
                    .first()
                )
                if user is not None:
                    user.role = TenantUserRole.TEACHER
                    promoted = True

        with tenant_db.get_session() as db_session:
            row = (
                db_session.query(PendingTeachSubmission)
                .filter(PendingTeachSubmission.id == submission_id)
                .first()
            )
            row.status = PendingSubmissionStatus.APPROVED
            row.reviewed_at = datetime.utcnow()
            row.reviewed_by = session.email
            row.promoted_to_teacher = promoted
            row.decision_notes = request.notes

        for record in data["attachment_keys"] or []:
            _delete_attachment(session.tenant_slug, record)

        _send_decision_email(
            instance_name=_get_tenant_instance_name(session),
            to_address=data["submitter_email"],
            decision="approved",
            notes=request.notes,
        )

        logger.info(
            "Admin %s approved submission %s (chunks=%d, promoted=%s)",
            session.email,
            submission_id,
            chunks_total,
            promoted,
        )
        return {
            "success": True,
            "submission_id": submission_id,
            "chunks_added": chunks_total,
            "files_archived": archived_files,
            "promoted_to_teacher": promoted,
        }

    @router.post("/{submission_id}/reject")
    def reject_submission(
        submission_id: str,
        request: RejectRequest,
        session=Depends(require_admin),
    ):
        from src.email.db_models import (
            PendingSubmissionStatus,
            PendingTeachSubmission,
        )

        tenant_db = _get_tenant_db(session)
        with tenant_db.get_session() as db_session:
            row = (
                db_session.query(PendingTeachSubmission)
                .filter(PendingTeachSubmission.id == submission_id)
                .first()
            )
            if row is None:
                raise HTTPException(status_code=404, detail="Submission not found")
            if row.status != PendingSubmissionStatus.PENDING:
                raise HTTPException(
                    status_code=409,
                    detail=f"Submission already {row.status.value}",
                )
            data = row.to_dict()
            row.status = PendingSubmissionStatus.REJECTED
            row.reviewed_at = datetime.utcnow()
            row.reviewed_by = session.email
            row.decision_notes = request.notes

        for record in data["attachment_keys"] or []:
            _delete_attachment(session.tenant_slug, record)

        _send_decision_email(
            instance_name=_get_tenant_instance_name(session),
            to_address=data["submitter_email"],
            decision="rejected",
            notes=request.notes,
        )

        logger.info(
            "Admin %s rejected submission %s",
            session.email,
            submission_id,
        )
        return {"success": True, "submission_id": submission_id}

    return router
