"""
Admin Audit Logger for RAGInbox.

Logs all admin actions to a dedicated audit log file.
"""

import logging
from pathlib import Path
from datetime import datetime
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
            action: Action performed (e.g., "whitelist_add", "document_delete")
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

    def log_whitelist_add(
        self, admin_email: str, whitelist_type: str, entry: str, success: bool
    ):
        """Log whitelist entry addition."""
        result = "success" if success else "failed"
        self.log_action(
            admin_email, "whitelist_add", f"{whitelist_type}:{entry}", result
        )

    def log_whitelist_remove(
        self, admin_email: str, whitelist_type: str, entry: str, success: bool
    ):
        """Log whitelist entry removal."""
        result = "success" if success else "failed"
        self.log_action(
            admin_email, "whitelist_remove", f"{whitelist_type}:{entry}", result
        )

    def log_document_delete(
        self, admin_email: str, filename: str, file_hash: str, success: bool
    ):
        """Log document deletion."""
        result = "success" if success else "failed"
        self.log_action(
            admin_email, "document_delete", filename, result, f"hash:{file_hash}"
        )

    def log_bulk_delete(
        self, admin_email: str, count: int, success_count: int, failed_count: int
    ):
        """Log bulk document deletion."""
        result = "partial" if failed_count > 0 else "success"
        self.log_action(
            admin_email,
            "document_bulk_delete",
            f"{count}_documents",
            result,
            f"succeeded:{success_count},failed:{failed_count}",
        )

    def log_access_denied(self, email: str, action: str, reason: str = "not_admin"):
        """Log denied admin access attempt."""
        self.log_action(email, action, "admin_panel", "denied", reason)

    def get_recent_logs(self, lines: int = 100) -> list[str]:
        """
        Get recent audit log entries.

        Args:
            lines: Number of recent lines to retrieve

        Returns:
            List of log entries (most recent first)
        """
        try:
            if not self.log_file.exists():
                return []

            with open(self.log_file, "r") as f:
                all_lines = f.readlines()

            # Return last N lines, reversed (most recent first)
            return list(reversed(all_lines[-lines:]))

        except Exception as e:
            logger.error(f"Error reading audit log: {e}")
            return []
