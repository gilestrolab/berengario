"""
Admin Audit Logger for Berengario.

Logs all admin actions to a dedicated audit log file.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AdminAuditLogger:
    """
    Logger for admin actions with structured output.

    Logs all administrative actions to data/logs/admin_audit.log
    with timestamp, admin email, action, target, and result.
    """

    def __init__(self, log_file: Path = None):
        """
        Initialize AdminAuditLogger.

        Args:
            log_file: Path to audit log file (default: data/logs/admin_audit.log)
        """
        if log_file is None:
            log_file = Path.cwd() / "data" / "logs" / "admin_audit.log"

        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"AdminAuditLogger initialized: {self.log_file}")

    def log_action(
        self,
        admin_email: str,
        action: str,
        target: str,
        result: str,
        details: Optional[str] = None,
    ):
        """
        Log an admin action.

        Args:
            admin_email: Email of admin performing action
            action: Action performed (e.g., "user_added", "document_delete")
            target: Target of action (e.g., "queriers", "document_hash")
            result: Result of action ("success", "failed", "denied")
            details: Optional additional details
        """
        timestamp = datetime.now().isoformat()

        # Format: [timestamp] [admin] [action] [target] [result] [details]
        log_entry = f"[{timestamp}] [{admin_email}] [{action}] [{target}] [{result}]"
        if details:
            log_entry += f" [{details}]"

        try:
            with open(self.log_file, "a") as f:
                f.write(log_entry + "\n")

            logger.debug(f"Audit log: {log_entry}")

        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

    def log_document_delete(
        self, admin_email: str, filename: str, file_hash: str, success: bool
    ):
        """Log document deletion."""
        result = "success" if success else "failed"
        self.log_action(
            admin_email, "document_delete", filename, result, f"hash:{file_hash}"
        )
