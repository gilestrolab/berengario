"""
Tenant management routes for the platform admin panel.

CRUD operations for tenants, user management, and key rotation.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from src.platform_admin.models import (
    TenantCreateRequest,
    TenantDetail,
    TenantStats,
    TenantSummary,
    TenantUserRequest,
    TenantUserResponse,
)
from src.platform_admin.routes.auth import AdminSessionManager

logger = logging.getLogger(__name__)


def _require_admin(request: Request, admin_session_manager: AdminSessionManager):
    """
    Validate admin session from request cookie.

    Args:
        request: FastAPI request.
        admin_session_manager: Admin session store.

    Returns:
        AdminSession.

    Raises:
        HTTPException: If not authenticated.
    """
    session_id = request.cookies.get("admin_session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = admin_session_manager.get(session_id)
    if not session or not session.authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session


def _human_size(nbytes: int) -> str:
    """
    Format byte count as human-readable string.

    Args:
        nbytes: Size in bytes.

    Returns:
        Human-readable size string (e.g., "12.3 MB").
    """
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


def _calc_dir_size(path) -> int:
    """
    Calculate total size of a directory recursively.

    Args:
        path: Directory path (str or Path).

    Returns:
        Total size in bytes.
    """
    from pathlib import Path

    total = 0
    p = Path(path)
    if not p.exists():
        return 0
    for f in p.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


def create_tenants_router(
    admin_session_manager: AdminSessionManager,
    db_manager,
    provisioner,
    key_manager=None,
    storage=None,
):
    """
    Create tenant management router.

    Args:
        admin_session_manager: Admin session store.
        db_manager: TenantDBManager instance.
        provisioner: TenantProvisioner instance.
        key_manager: DatabaseKeyManager instance (optional).
        storage: StorageBackend instance (optional, for disk usage).

    Returns:
        Configured APIRouter.
    """
    router = APIRouter(prefix="/api/tenants", tags=["tenants"])

    @router.get("/", response_model=list[TenantSummary])
    async def list_tenants(request: Request):
        """
        List all tenants with user counts.

        Args:
            request: FastAPI request.

        Returns:
            List of TenantSummary.
        """
        _require_admin(request, admin_session_manager)

        from sqlalchemy import func

        from src.platform.models import Tenant, TenantUser

        with db_manager.get_platform_session() as session:
            results = (
                session.query(
                    Tenant,
                    func.count(TenantUser.id).label("user_count"),
                )
                .outerjoin(TenantUser, Tenant.id == TenantUser.tenant_id)
                .group_by(Tenant.id)
                .order_by(Tenant.created_at.desc())
                .all()
            )

            return [
                TenantSummary(
                    id=str(t.id),
                    slug=t.slug,
                    name=t.name,
                    status=t.status.value,
                    organization=t.organization,
                    email_address=t.email_address,
                    user_count=count,
                    created_at=t.created_at.isoformat() if t.created_at else "",
                )
                for t, count in results
            ]

    @router.get("/{slug}", response_model=TenantDetail)
    async def get_tenant(slug: str, request: Request):
        """
        Get detailed tenant information.

        Args:
            slug: Tenant slug.
            request: FastAPI request.

        Returns:
            TenantDetail.
        """
        _require_admin(request, admin_session_manager)

        from src.platform.models import Tenant, TenantUser

        with db_manager.get_platform_session() as session:
            tenant = session.query(Tenant).filter(Tenant.slug == slug).first()
            if not tenant:
                raise HTTPException(status_code=404, detail="Tenant not found")

            users = (
                session.query(TenantUser)
                .filter(TenantUser.tenant_id == tenant.id)
                .all()
            )

            # Test DB health
            db_healthy = False
            try:
                db_healthy = db_manager.test_tenant_connection(tenant.db_name)
            except Exception:
                pass

            return TenantDetail(
                id=str(tenant.id),
                slug=tenant.slug,
                name=tenant.name,
                description=tenant.description,
                organization=tenant.organization,
                status=tenant.status.value,
                email_address=tenant.email_address,
                email_display_name=tenant.email_display_name,
                db_name=tenant.db_name,
                storage_path=tenant.storage_path,
                db_healthy=db_healthy,
                user_count=len(users),
                users=[
                    TenantUserResponse(
                        id=u.id,
                        email=u.email,
                        role=u.role.value if hasattr(u.role, "value") else u.role,
                        tenant_id=str(u.tenant_id),
                        created_at=(u.created_at.isoformat() if u.created_at else ""),
                    )
                    for u in users
                ],
                chunk_size=tenant.chunk_size,
                chunk_overlap=tenant.chunk_overlap,
                top_k_retrieval=tenant.top_k_retrieval,
                similarity_threshold=tenant.similarity_threshold,
                llm_model=tenant.llm_model,
                invite_code=tenant.invite_code,
                created_at=tenant.created_at.isoformat() if tenant.created_at else "",
                updated_at=(
                    tenant.updated_at.isoformat() if tenant.updated_at else None
                ),
            )

    @router.post("/", response_model=TenantSummary)
    async def create_tenant(body: TenantCreateRequest, request: Request):
        """
        Create a new tenant.

        Args:
            body: Tenant creation request.
            request: FastAPI request.

        Returns:
            TenantSummary of created tenant.
        """
        _require_admin(request, admin_session_manager)

        try:
            tenant = provisioner.create_tenant(
                slug=body.slug,
                name=body.name,
                admin_email=body.admin_email,
                description=body.description,
                organization=body.organization,
                custom_prompt=body.custom_prompt,
                llm_model=body.llm_model,
            )
            logger.info(f"Admin created tenant: {body.slug}")
            return TenantSummary(
                id=str(tenant.id),
                slug=tenant.slug,
                name=tenant.name,
                status=tenant.status.value,
                organization=tenant.organization,
                email_address=tenant.email_address,
                user_count=1,  # Admin user just created
                created_at=tenant.created_at.isoformat() if tenant.created_at else "",
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to create tenant {body.slug}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/{slug}/suspend")
    async def suspend_tenant(slug: str, request: Request):
        """
        Suspend a tenant.

        Args:
            slug: Tenant slug.
            request: FastAPI request.

        Returns:
            Success message.
        """
        _require_admin(request, admin_session_manager)

        try:
            provisioner.suspend_tenant(slug)
            logger.info(f"Admin suspended tenant: {slug}")
            return {"success": True, "message": f"Tenant '{slug}' suspended"}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/{slug}/resume")
    async def resume_tenant(slug: str, request: Request):
        """
        Resume a suspended tenant.

        Args:
            slug: Tenant slug.
            request: FastAPI request.

        Returns:
            Success message.
        """
        _require_admin(request, admin_session_manager)

        try:
            provisioner.resume_tenant(slug)
            logger.info(f"Admin resumed tenant: {slug}")
            return {"success": True, "message": f"Tenant '{slug}' resumed"}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.delete("/{slug}")
    async def delete_tenant(
        slug: str,
        request: Request,
        confirm: Optional[str] = Query(None),
    ):
        """
        Permanently delete a tenant.

        Requires ?confirm={slug} query parameter as safety check.

        Args:
            slug: Tenant slug.
            request: FastAPI request.
            confirm: Confirmation slug (must match).

        Returns:
            Success message.
        """
        _require_admin(request, admin_session_manager)

        if confirm != slug:
            raise HTTPException(
                status_code=400,
                detail=f"Confirmation required: add ?confirm={slug} to confirm deletion",
            )

        try:
            provisioner.delete_tenant(slug)
            logger.warning(f"Admin deleted tenant: {slug}")
            return {"success": True, "message": f"Tenant '{slug}' deleted permanently"}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/{slug}/rotate-key")
    async def rotate_key(slug: str, request: Request):
        """
        Rotate encryption key for a tenant.

        Args:
            slug: Tenant slug.
            request: FastAPI request.

        Returns:
            Success message.
        """
        _require_admin(request, admin_session_manager)

        if not key_manager:
            raise HTTPException(status_code=400, detail="Encryption is not enabled")

        from src.platform.models import Tenant

        with db_manager.get_platform_session() as session:
            tenant = session.query(Tenant).filter(Tenant.slug == slug).first()
            if not tenant:
                raise HTTPException(status_code=404, detail="Tenant not found")

            try:
                key_manager.rotate_tenant_key_with_session(session, tenant.id)
                logger.info(f"Admin rotated encryption key for tenant: {slug}")
                return {
                    "success": True,
                    "message": f"Encryption key rotated for '{slug}'",
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{slug}/users", response_model=list[TenantUserResponse])
    async def list_users(slug: str, request: Request):
        """
        List users in a tenant.

        Args:
            slug: Tenant slug.
            request: FastAPI request.

        Returns:
            List of TenantUserResponse.
        """
        _require_admin(request, admin_session_manager)

        try:
            users = provisioner.get_tenant_users(slug)
            return [
                TenantUserResponse(
                    id=u["id"],
                    email=u["email"],
                    role=u["role"],
                    tenant_id=u["tenant_id"],
                    created_at=u.get("created_at", ""),
                )
                for u in users
            ]
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/{slug}/users", response_model=TenantUserResponse)
    async def add_user(slug: str, body: TenantUserRequest, request: Request):
        """
        Add a user to a tenant.

        Args:
            slug: Tenant slug.
            body: User creation request.
            request: FastAPI request.

        Returns:
            TenantUserResponse.
        """
        _require_admin(request, admin_session_manager)

        from src.platform.models import TenantUserRole

        role_map = {
            "admin": TenantUserRole.ADMIN,
            "teacher": TenantUserRole.TEACHER,
            "querier": TenantUserRole.QUERIER,
        }
        role = role_map.get(body.role, TenantUserRole.QUERIER)

        try:
            user = provisioner.add_user(slug, body.email, role)
            logger.info(f"Admin added user {body.email} to tenant {slug}")
            return TenantUserResponse(
                id=user.id or 0,
                email=user.email,
                role=user.role.value if hasattr(user.role, "value") else user.role,
                tenant_id=str(user.tenant_id),
                created_at=(user.created_at.isoformat() if user.created_at else ""),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.delete("/{slug}/users/{email}")
    async def remove_user(slug: str, email: str, request: Request):
        """
        Remove a user from a tenant.

        Args:
            slug: Tenant slug.
            email: User email to remove.
            request: FastAPI request.

        Returns:
            Success message.
        """
        _require_admin(request, admin_session_manager)

        try:
            removed = provisioner.remove_user(slug, email)
            if not removed:
                raise HTTPException(
                    status_code=404, detail=f"User {email} not found in tenant {slug}"
                )
            logger.info(f"Admin removed user {email} from tenant {slug}")
            return {"success": True, "message": f"User {email} removed from {slug}"}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/{slug}/stats", response_model=TenantStats)
    async def get_tenant_stats(slug: str, request: Request):
        """
        Get usage statistics for a tenant.

        Queries the tenant database for query counts, document stats,
        feedback, and email processing metrics. Also calculates disk usage.

        Args:
            slug: Tenant slug.
            request: FastAPI request.

        Returns:
            TenantStats.
        """
        _require_admin(request, admin_session_manager)

        from src.platform.models import Tenant

        # Look up tenant
        with db_manager.get_platform_session() as session:
            tenant = session.query(Tenant).filter(Tenant.slug == slug).first()
            if not tenant:
                raise HTTPException(status_code=404, detail="Tenant not found")
            db_name = tenant.db_name
            tenant_slug = tenant.slug
            storage_path = tenant.storage_path

        stats = TenantStats(slug=tenant_slug)

        # Query tenant database for usage stats
        try:
            with db_manager.get_tenant_session_by_name(db_name) as tsession:
                from sqlalchemy import text

                # Query counts from conversation_messages table
                try:
                    row = tsession.execute(
                        text(
                            "SELECT "
                            "  COUNT(CASE WHEN message_type = 'query' THEN 1 END) AS queries, "
                            "  COUNT(CASE WHEN message_type = 'reply' THEN 1 END) AS replies "
                            "FROM conversation_messages"
                        )
                    ).first()
                    if row:
                        stats.total_queries = row.queries or 0
                        stats.total_replies = row.replies or 0
                except Exception:
                    pass

                # Conversation count and unique users
                try:
                    row = tsession.execute(
                        text(
                            "SELECT COUNT(*) AS convos, "
                            "  COUNT(DISTINCT sender) AS users "
                            "FROM conversations"
                        )
                    ).first()
                    if row:
                        stats.total_conversations = row.convos or 0
                        stats.unique_users = row.users or 0
                except Exception:
                    pass

                # Document stats from document_descriptions
                try:
                    rows = tsession.execute(
                        text(
                            "SELECT file_type, COUNT(*) AS cnt, "
                            "  COALESCE(SUM(file_size), 0) AS total_size, "
                            "  COALESCE(SUM(chunk_count), 0) AS chunks "
                            "FROM document_descriptions "
                            "GROUP BY file_type"
                        )
                    ).all()
                    by_type = {}
                    total_docs = 0
                    total_size = 0
                    total_chunks = 0
                    for r in rows:
                        ft = r.file_type or "unknown"
                        # Normalise: ensure dot prefix (.pdf not pdf)
                        if ft != "unknown" and not ft.startswith("."):
                            ft = f".{ft}"
                        by_type[ft] = by_type.get(ft, 0) + int(r.cnt)
                        total_docs += int(r.cnt)
                        total_size += int(r.total_size)
                        total_chunks += int(r.chunks)
                    stats.total_documents = total_docs
                    stats.total_document_bytes = total_size
                    stats.total_chunks = total_chunks
                    stats.documents_by_type = by_type
                except Exception:
                    pass

                # Feedback stats
                try:
                    row = tsession.execute(
                        text(
                            "SELECT COUNT(*) AS total, "
                            "  SUM(CASE WHEN is_positive = 1 THEN 1 ELSE 0 END) AS positive "
                            "FROM response_feedback"
                        )
                    ).first()
                    if row:
                        stats.total_feedback = int(row.total or 0)
                        stats.positive_feedback = int(row.positive or 0)
                except Exception:
                    pass

                # Email processing stats
                try:
                    row = tsession.execute(
                        text(
                            "SELECT COUNT(*) AS total, "
                            "  SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors "
                            "FROM processed_messages"
                        )
                    ).first()
                    if row:
                        stats.emails_processed = int(row.total or 0)
                        stats.emails_errors = int(row.errors or 0)
                except Exception:
                    pass

                # Activity range
                try:
                    row = tsession.execute(
                        text(
                            "SELECT MIN(timestamp) AS first_ts, "
                            "  MAX(timestamp) AS last_ts "
                            "FROM conversation_messages"
                        )
                    ).first()
                    if row and row.first_ts:
                        stats.first_activity = str(row.first_ts)
                        stats.last_activity = str(row.last_ts)
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"Failed to query tenant DB for {slug}: {e}")

        # Disk usage from storage
        try:
            if storage and hasattr(storage, "get_tenant_path"):
                tenant_path = storage.get_tenant_path(tenant_slug)
                stats.disk_usage_bytes = _calc_dir_size(tenant_path)
            elif storage_path:
                from pathlib import Path

                stats.disk_usage_bytes = _calc_dir_size(Path("data") / storage_path)
            stats.disk_usage_human = _human_size(stats.disk_usage_bytes)
        except Exception as e:
            logger.warning(f"Failed to calc disk usage for {slug}: {e}")

        return stats

    return router
