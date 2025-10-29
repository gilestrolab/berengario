"""
Email whitelist validator for security.

This module provides whitelist validation to control which email addresses
are allowed to contribute documents to the knowledge base. Supports both
individual email addresses and domain-based whitelisting.
"""

import logging
from pathlib import Path
from typing import List, Set

from src.config import settings

logger = logging.getLogger(__name__)


class WhitelistValidator:
    """
    Validates email addresses against a whitelist.

    Supports:
    - Individual email addresses (alice@example.com)
    - Domain wildcards (@imperial.ac.uk)
    - File-based whitelist
    - Inline whitelist (comma-separated)

    Examples:
        >>> validator = WhitelistValidator()
        >>> validator.is_allowed("alice@imperial.ac.uk")
        True  # If @imperial.ac.uk is in whitelist
        >>> validator.is_allowed("bob@spam.com")
        False  # Not in whitelist
    """

    def __init__(
        self,
        whitelist: str = None,
        whitelist_file: Path = None,
        enabled: bool = None,
    ):
        """
        Initialize whitelist validator.

        Args:
            whitelist: Comma-separated list of allowed addresses/domains
            whitelist_file: Path to file with allowed addresses/domains
            enabled: Whether whitelist validation is enabled
        """
        self.enabled = enabled if enabled is not None else settings.email_whitelist_enabled
        self.whitelist_entries: Set[str] = set()
        self.domain_entries: Set[str] = set()

        if not self.enabled:
            logger.warning("Email whitelist validation is DISABLED - all senders allowed!")
            return

        # Load from inline whitelist
        inline = whitelist or settings.email_whitelist
        if inline:
            self._load_from_string(inline)

        # Load from file
        file_path = whitelist_file or settings.email_whitelist_file
        if file_path:
            self._load_from_file(file_path)

        # Log configuration
        if self.whitelist_entries or self.domain_entries:
            logger.info(
                f"Whitelist initialized: {len(self.whitelist_entries)} addresses, "
                f"{len(self.domain_entries)} domains"
            )
        else:
            logger.warning("Whitelist is enabled but empty - no emails will be allowed!")

    def _load_from_string(self, whitelist_str: str) -> None:
        """
        Load whitelist from comma-separated string.

        Args:
            whitelist_str: Comma-separated whitelist entries
        """
        entries = [entry.strip() for entry in whitelist_str.split(",") if entry.strip()]

        for entry in entries:
            if entry.startswith("@"):
                # Domain entry
                self.domain_entries.add(entry.lower())
                logger.debug(f"Added domain to whitelist: {entry}")
            elif "@" in entry:
                # Email address
                self.whitelist_entries.add(entry.lower())
                logger.debug(f"Added email to whitelist: {entry}")
            else:
                logger.warning(f"Invalid whitelist entry (skipped): {entry}")

    def _load_from_file(self, file_path: Path) -> None:
        """
        Load whitelist from file.

        File format:
        - One entry per line
        - Lines starting with # are comments
        - Empty lines are ignored
        - Supports both email addresses and @domain entries

        Args:
            file_path: Path to whitelist file
        """
        try:
            if not file_path.exists():
                logger.error(f"Whitelist file not found: {file_path}")
                return

            logger.info(f"Loading whitelist from file: {file_path}")

            with open(file_path, "r") as f:
                for line_num, line in enumerate(f, 1):
                    # Remove comments and whitespace
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    # Process entry
                    if line.startswith("@"):
                        self.domain_entries.add(line.lower())
                        logger.debug(f"Line {line_num}: Added domain {line}")
                    elif "@" in line:
                        self.whitelist_entries.add(line.lower())
                        logger.debug(f"Line {line_num}: Added email {line}")
                    else:
                        logger.warning(f"Line {line_num}: Invalid entry (skipped): {line}")

        except Exception as e:
            logger.error(f"Error loading whitelist file: {e}")

    def is_allowed(self, email_address: str) -> bool:
        """
        Check if an email address is allowed.

        Args:
            email_address: Email address to validate

        Returns:
            True if allowed, False otherwise
        """
        if not self.enabled:
            # Whitelist disabled - allow all
            return True

        if not email_address:
            logger.warning("Empty email address provided for validation")
            return False

        email_lower = email_address.lower().strip()

        # Check exact email match
        if email_lower in self.whitelist_entries:
            logger.debug(f"Email allowed (exact match): {email_address}")
            return True

        # Check domain match
        if "@" in email_lower:
            domain = "@" + email_lower.split("@")[1]
            if domain in self.domain_entries:
                logger.debug(f"Email allowed (domain match): {email_address} via {domain}")
                return True

        # Not in whitelist
        logger.info(f"Email REJECTED (not in whitelist): {email_address}")
        return False

    def get_whitelist_summary(self) -> dict:
        """
        Get summary of whitelist configuration.

        Returns:
            Dictionary with whitelist statistics
        """
        return {
            "enabled": self.enabled,
            "email_count": len(self.whitelist_entries),
            "domain_count": len(self.domain_entries),
            "emails": sorted(list(self.whitelist_entries)),
            "domains": sorted(list(self.domain_entries)),
        }

    def add_entry(self, entry: str) -> bool:
        """
        Add an entry to the whitelist (runtime only, not persisted).

        Args:
            entry: Email address or domain to add

        Returns:
            True if added successfully, False otherwise
        """
        entry = entry.strip().lower()

        if entry.startswith("@"):
            if entry in self.domain_entries:
                logger.info(f"Domain already in whitelist: {entry}")
                return False
            self.domain_entries.add(entry)
            logger.info(f"Added domain to whitelist: {entry}")
            return True
        elif "@" in entry:
            if entry in self.whitelist_entries:
                logger.info(f"Email already in whitelist: {entry}")
                return False
            self.whitelist_entries.add(entry)
            logger.info(f"Added email to whitelist: {entry}")
            return True
        else:
            logger.warning(f"Invalid entry format: {entry}")
            return False

    def remove_entry(self, entry: str) -> bool:
        """
        Remove an entry from the whitelist (runtime only, not persisted).

        Args:
            entry: Email address or domain to remove

        Returns:
            True if removed successfully, False if not found
        """
        entry = entry.strip().lower()

        if entry.startswith("@"):
            if entry in self.domain_entries:
                self.domain_entries.remove(entry)
                logger.info(f"Removed domain from whitelist: {entry}")
                return True
        elif "@" in entry:
            if entry in self.whitelist_entries:
                self.whitelist_entries.remove(entry)
                logger.info(f"Removed email from whitelist: {entry}")
                return True

        logger.warning(f"Entry not found in whitelist: {entry}")
        return False


# Global validator instance
whitelist_validator = WhitelistValidator()
