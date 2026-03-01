"""
Platform Admin — self-contained FastAPI application.

Provides a web UI and API for managing tenants, users, and platform health.
Shares only the platform database and src/platform/ module with the main app.
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.auth.otp_manager import OTPManager
from src.config import settings
from src.platform.db_manager import TenantDBManager
from src.platform.encryption import DatabaseKeyManager
from src.platform.provisioning import TenantProvisioner
from src.platform.storage import create_storage_backend
from src.platform_admin.routes.auth import AdminSessionManager, create_admin_auth_router
from src.platform_admin.routes.health import create_health_router
from src.platform_admin.routes.tenants import create_tenants_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Initialize platform-level dependencies
# ---------------------------------------------------------------------------

db_manager = TenantDBManager()
db_manager.init_platform_db()

storage = create_storage_backend()

key_manager = None
if settings.master_encryption_key:
    key_manager = DatabaseKeyManager(settings.master_encryption_key)

provisioner = TenantProvisioner(db_manager, storage, key_manager)

# Auth components
otp_manager = OTPManager()
admin_session_manager = AdminSessionManager(timeout=settings.web_session_timeout)
admin_emails = settings.get_platform_admin_emails()

# Email sender for OTP delivery
try:
    from src.email.email_sender import EmailSender

    email_sender = EmailSender(
        smtp_server=settings.smtp_server,
        smtp_port=settings.smtp_port,
        smtp_user=settings.smtp_user,
        smtp_password=settings.smtp_password,
        use_tls=settings.smtp_use_tls,
        from_address=settings.email_target_address,
        from_name=f"{settings.instance_name} Platform Admin",
    )
except Exception as e:
    logger.warning(f"Email sender unavailable: {e}. OTP emails will fail.")
    email_sender = None

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title=f"{settings.instance_name} Platform Admin",
    description="Platform administration for multi-tenant Berengario deployments",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Mount routes
# ---------------------------------------------------------------------------

auth_router = create_admin_auth_router(
    otp_manager=otp_manager,
    admin_session_manager=admin_session_manager,
    admin_emails=admin_emails,
    email_sender=email_sender,
    settings=settings,
)

tenants_router = create_tenants_router(
    admin_session_manager=admin_session_manager,
    db_manager=db_manager,
    provisioner=provisioner,
    key_manager=key_manager,
    storage=storage,
)

health_router = create_health_router(
    admin_session_manager=admin_session_manager,
    db_manager=db_manager,
    settings=settings,
)

app.include_router(auth_router)
app.include_router(tenants_router)
app.include_router(health_router)

# Static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------


@app.get("/")
async def root():
    """Redirect to login page."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/static/login.html")


@app.on_event("shutdown")
async def shutdown():
    """Clean up resources on shutdown."""
    db_manager.close()
    logger.info("Platform admin shutdown complete")
