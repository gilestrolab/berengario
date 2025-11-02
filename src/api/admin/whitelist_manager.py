"""
Whitelist Manager for admin interface.

Handles reading, writing, and managing whitelist files while preserving comments.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class WhitelistManager:
    """
    Manager for whitelist file operations.

    Handles reading, parsing, and writing whitelist files while preserving
    comments and formatting. Validates email addresses and domain wildcards.
    """

    # Whitelist types and their file paths
    WHITELIST_TYPES = {
        "queriers": "data/config/allowed_queriers.txt",
        "teachers": "data/config/allowed_teachers.txt",
        "admins": "data/config/allowed_admins.txt",
    }

    # Email validation regex (simplified)
    EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    DOMAIN_REGEX = re.compile(r"^@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    def __init__(self, base_path: Path = None):
        """
        Initialize WhitelistManager.

        Args:
            base_path: Base path for whitelist files (default: project root)
        """
        self.base_path = base_path or Path.cwd()
        logger.info("WhitelistManager initialized")

    def get_whitelist_path(self, whitelist_type: str) -> Path:
        """
        Get full path to whitelist file.

        Args:
            whitelist_type: Type of whitelist (queriers, teachers, admins)

        Returns:
            Path to whitelist file

        Raises:
            ValueError: If whitelist type is invalid
        """
        if whitelist_type not in self.WHITELIST_TYPES:
            raise ValueError(
                f"Invalid whitelist type: {whitelist_type}. "
                f"Must be one of: {', '.join(self.WHITELIST_TYPES.keys())}"
            )

        return self.base_path / self.WHITELIST_TYPES[whitelist_type]

    def read_whitelist(self, whitelist_type: str) -> Dict[str, any]:
        """
        Read and parse whitelist file.

        Args:
            whitelist_type: Type of whitelist to read

        Returns:
            Dictionary with:
                - entries: List of email addresses/domains
                - comments: List of comment lines (for preservation)
                - raw_lines: Original file lines
        """
        path = self.get_whitelist_path(whitelist_type)

        if not path.exists():
            logger.warning(f"Whitelist file not found: {path}")
            return {"entries": [], "comments": [], "raw_lines": []}

        try:
            with open(path, "r") as f:
                raw_lines = f.readlines()

            entries = []
            comments = []

            for line in raw_lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    comments.append(line)
                else:
                    # Extract email/domain (ignore inline comments)
                    entry = line.split("#")[0].strip()
                    if entry:
                        entries.append(entry)

            logger.info(f"Read {len(entries)} entries from {whitelist_type} whitelist")

            return {
                "entries": entries,
                "comments": comments,
                "raw_lines": raw_lines,
            }

        except Exception as e:
            logger.error(f"Error reading whitelist {whitelist_type}: {e}")
            raise

    def write_whitelist(
        self, whitelist_type: str, entries: List[str], preserve_comments: bool = True
    ) -> bool:
        """
        Write whitelist file with entries.

        Args:
            whitelist_type: Type of whitelist to write
            entries: List of email addresses/domains to write
            preserve_comments: Whether to preserve existing comments

        Returns:
            True if successful

        Raises:
            ValueError: If entries contain invalid formats
        """
        path = self.get_whitelist_path(whitelist_type)

        # Validate all entries first
        for entry in entries:
            if not self.validate_entry(entry):
                raise ValueError(f"Invalid whitelist entry: {entry}")

        try:
            # Read existing comments if preserving
            comments = []
            if preserve_comments and path.exists():
                existing = self.read_whitelist(whitelist_type)
                comments = existing["comments"]

            # Build new file content
            lines = []

            # Add comments
            if comments:
                for comment in comments:
                    if comment:  # Skip empty lines
                        lines.append(comment)
                lines.append("")  # Blank line after comments

            # Add entries (one per line)
            for entry in sorted(set(entries)):  # Remove duplicates and sort
                lines.append(entry)

            # Write to file
            with open(path, "w") as f:
                f.write("\n".join(lines) + "\n")

            logger.info(f"Wrote {len(entries)} entries to {whitelist_type} whitelist")
            return True

        except Exception as e:
            logger.error(f"Error writing whitelist {whitelist_type}: {e}")
            raise

    def add_entry(self, whitelist_type: str, entry: str) -> bool:
        """
        Add entry to whitelist.

        Args:
            whitelist_type: Type of whitelist
            entry: Email address or domain to add

        Returns:
            True if entry was added, False if already exists
        """
        if not self.validate_entry(entry):
            raise ValueError(f"Invalid whitelist entry: {entry}")

        data = self.read_whitelist(whitelist_type)
        entries = data["entries"]

        # Normalize entry (lowercase)
        entry = entry.lower().strip()

        if entry in entries:
            logger.info(f"Entry already exists in {whitelist_type}: {entry}")
            return False

        entries.append(entry)
        self.write_whitelist(whitelist_type, entries)

        logger.info(f"Added entry to {whitelist_type}: {entry}")
        return True

    def remove_entry(self, whitelist_type: str, entry: str) -> bool:
        """
        Remove entry from whitelist.

        Args:
            whitelist_type: Type of whitelist
            entry: Email address or domain to remove

        Returns:
            True if entry was removed, False if not found
        """
        data = self.read_whitelist(whitelist_type)
        entries = data["entries"]

        # Normalize entry (lowercase)
        entry = entry.lower().strip()

        if entry not in entries:
            logger.info(f"Entry not found in {whitelist_type}: {entry}")
            return False

        entries.remove(entry)
        self.write_whitelist(whitelist_type, entries)

        logger.info(f"Removed entry from {whitelist_type}: {entry}")
        return True

    def validate_entry(self, entry: str) -> bool:
        """
        Validate whitelist entry format.

        Args:
            entry: Email address or domain wildcard to validate

        Returns:
            True if valid, False otherwise
        """
        entry = entry.strip()

        # Check if it's a domain wildcard (@domain.com)
        if entry.startswith("@"):
            return bool(self.DOMAIN_REGEX.match(entry))

        # Otherwise, validate as email address
        return bool(self.EMAIL_REGEX.match(entry))

    def get_entry_type(self, entry: str) -> str:
        """
        Determine if entry is an email or domain wildcard.

        Args:
            entry: Entry to check

        Returns:
            "domain" or "email"
        """
        return "domain" if entry.startswith("@") else "email"

    def count_entries(self, whitelist_type: str) -> Tuple[int, int]:
        """
        Count entries in whitelist.

        Args:
            whitelist_type: Type of whitelist

        Returns:
            Tuple of (email_count, domain_count)
        """
        data = self.read_whitelist(whitelist_type)
        entries = data["entries"]

        emails = [e for e in entries if not e.startswith("@")]
        domains = [e for e in entries if e.startswith("@")]

        return len(emails), len(domains)
