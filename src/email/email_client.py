"""
IMAP email client for inbox monitoring.

This module provides an IMAP client for connecting to email servers,
fetching messages, and managing inbox operations. Supports SSL/TLS
connections with automatic reconnection on failures.
"""

import logging
import time
from typing import List, Optional, Tuple

from imap_tools import MailBox, MailBoxUnencrypted, MailMessage
from imap_tools.errors import MailboxLoginError, MailboxLogoutError

from src.config import settings

logger = logging.getLogger(__name__)


class EmailClientError(Exception):
    """Base exception for email client errors."""

    pass


class EmailConnectionError(EmailClientError):
    """Exception raised for connection errors."""

    pass


class EmailAuthenticationError(EmailClientError):
    """Exception raised for authentication errors."""

    pass


class EmailClient:
    """
    IMAP email client with connection management and auto-reconnection.

    This class handles IMAP connections to email servers with support for:
    - SSL/TLS encrypted connections
    - Automatic reconnection on failures
    - Connection health checking
    - Message fetching and marking

    Attributes:
        server: IMAP server address
        port: IMAP server port
        username: Email account username
        password: Email account password
        use_ssl: Whether to use SSL/TLS encryption
    """

    def __init__(
        self,
        server: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_ssl: Optional[bool] = None,
    ):
        """
        Initialize email client.

        Args:
            server: IMAP server address (defaults to settings)
            port: IMAP server port (defaults to settings)
            username: Email username (defaults to settings)
            password: Email password (defaults to settings)
            use_ssl: Use SSL/TLS (defaults to settings)
        """
        self.server = server or settings.imap_server
        self.port = port or settings.imap_port
        self.username = username or settings.imap_user
        self.password = password or settings.imap_password
        self.use_ssl = use_ssl if use_ssl is not None else settings.imap_use_ssl

        self._mailbox: Optional[MailBox] = None
        self._connected = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 3
        self._reconnect_delay = 5  # seconds

        logger.info(f"EmailClient initialized for {self.username}@{self.server}")

    def connect(self) -> bool:
        """
        Connect to IMAP server.

        Returns:
            True if connection successful, False otherwise.

        Raises:
            EmailAuthenticationError: If authentication fails.
            EmailConnectionError: If connection fails.
        """
        if self._connected and self._mailbox is not None:
            logger.debug("Already connected to IMAP server")
            return True

        try:
            logger.info(f"Connecting to IMAP server {self.server}:{self.port}")

            # Create mailbox connection with 60 second timeout
            timeout = 60  # seconds - prevents hanging on slow/unresponsive servers
            if self.use_ssl:
                self._mailbox = MailBox(self.server, self.port, timeout=timeout)
            else:
                # Unencrypted connection - use STARTTLS if on standard port 143
                self._mailbox = MailBoxUnencrypted(
                    self.server, self.port, timeout=timeout
                )
                if self.port == 143:
                    # Upgrade to TLS using STARTTLS
                    logger.debug("Upgrading connection with STARTTLS")
                    self._mailbox.client.starttls()

            # Login
            self._mailbox.login(self.username, self.password)

            self._connected = True
            self._reconnect_attempts = 0
            logger.info("Successfully connected to IMAP server")
            return True

        except MailboxLoginError as e:
            logger.error(f"IMAP authentication failed: {e}")
            self._connected = False
            raise EmailAuthenticationError(f"Authentication failed: {e}") from e

        except Exception as e:
            logger.error(f"IMAP connection failed: {e}")
            self._connected = False
            raise EmailConnectionError(f"Connection failed: {e}") from e

    def disconnect(self) -> None:
        """
        Disconnect from IMAP server.

        Safely closes the IMAP connection and cleans up resources.
        """
        if self._mailbox is not None:
            try:
                logger.info("Disconnecting from IMAP server")
                self._mailbox.logout()
            except MailboxLogoutError as e:
                logger.warning(f"Error during logout: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error during logout: {e}")
            finally:
                self._mailbox = None
                self._connected = False
                logger.info("Disconnected from IMAP server")

    def is_connected(self) -> bool:
        """
        Check if client is connected to IMAP server.

        Performs a quick health check by attempting a NOOP command.

        Returns:
            True if connected and healthy, False otherwise.
        """
        if not self._connected or self._mailbox is None:
            return False

        try:
            # Try a NOOP command to verify connection is alive
            self._mailbox.client.noop()
            return True
        except Exception as e:
            logger.warning(f"Connection health check failed: {e}")
            self._connected = False
            return False

    def reconnect(self) -> bool:
        """
        Attempt to reconnect to IMAP server.

        Uses exponential backoff for reconnection attempts.

        Returns:
            True if reconnection successful, False otherwise.
        """
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error(
                f"Max reconnection attempts ({self._max_reconnect_attempts}) reached"
            )
            return False

        self._reconnect_attempts += 1
        delay = self._reconnect_delay * self._reconnect_attempts

        logger.info(
            f"Reconnection attempt {self._reconnect_attempts}/{self._max_reconnect_attempts} "
            f"after {delay}s delay"
        )
        time.sleep(delay)

        # Disconnect first
        self.disconnect()

        # Try to reconnect
        try:
            return self.connect()
        except (EmailAuthenticationError, EmailConnectionError) as e:
            logger.error(f"Reconnection failed: {e}")
            return False

    def ensure_connected(self) -> None:
        """
        Ensure client is connected, reconnect if necessary.

        Raises:
            EmailConnectionError: If unable to establish connection.
        """
        if self.is_connected():
            return

        logger.warning("Connection lost, attempting to reconnect")

        if not self.reconnect():
            raise EmailConnectionError(
                "Unable to establish connection after reconnection attempts"
            )

    def fetch_unread(
        self, folder: str = "INBOX", limit: Optional[int] = None
    ) -> List[MailMessage]:
        """
        Fetch unread messages from specified folder.

        Args:
            folder: Email folder to check (default: INBOX)
            limit: Maximum number of messages to fetch (None = all)

        Returns:
            List of unread MailMessage objects.

        Raises:
            EmailConnectionError: If not connected.
        """
        self.ensure_connected()

        try:
            logger.info(f"Fetching unread messages from {folder}")

            # Select folder
            self._mailbox.folder.set(folder)

            # Fetch unread messages
            messages = list(
                self._mailbox.fetch(criteria="UNSEEN", limit=limit, mark_seen=False)
            )

            logger.info(f"Found {len(messages)} unread messages")
            return messages

        except Exception as e:
            logger.error(f"Error fetching unread messages: {e}")
            self._connected = False
            raise EmailConnectionError(f"Failed to fetch messages: {e}") from e

    def mark_seen(self, message_uid: str) -> bool:
        """
        Mark a message as seen/read.

        Args:
            message_uid: UID of the message to mark.

        Returns:
            True if successful, False otherwise.
        """
        self.ensure_connected()

        try:
            logger.debug(f"Marking message {message_uid} as seen")
            self._mailbox.flag(message_uid, ["\\Seen"], True)
            return True

        except Exception as e:
            logger.error(f"Error marking message as seen: {e}")
            return False

    def mark_unseen(self, message_uid: str) -> bool:
        """
        Mark a message as unseen/unread.

        Args:
            message_uid: UID of the message to mark.

        Returns:
            True if successful, False otherwise.
        """
        self.ensure_connected()

        try:
            logger.debug(f"Marking message {message_uid} as unseen")
            self._mailbox.flag(message_uid, ["\\Seen"], False)
            return True

        except Exception as e:
            logger.error(f"Error marking message as unseen: {e}")
            return False

    def get_folder_list(self) -> List[str]:
        """
        Get list of available folders.

        Returns:
            List of folder names.

        Raises:
            EmailConnectionError: If not connected.
        """
        self.ensure_connected()

        try:
            folders = [folder.name for folder in self._mailbox.folder.list()]
            logger.debug(f"Found {len(folders)} folders")
            return folders

        except Exception as e:
            logger.error(f"Error fetching folder list: {e}")
            raise EmailConnectionError(f"Failed to fetch folders: {e}") from e

    def get_message_count(self, folder: str = "INBOX") -> Tuple[int, int]:
        """
        Get message counts for a folder.

        Args:
            folder: Folder to check (default: INBOX)

        Returns:
            Tuple of (total_messages, unread_messages)

        Raises:
            EmailConnectionError: If not connected.
        """
        self.ensure_connected()

        try:
            self._mailbox.folder.set(folder)

            # Get total count
            total = len(list(self._mailbox.fetch(criteria="ALL", mark_seen=False)))

            # Get unread count
            unread = len(list(self._mailbox.fetch(criteria="UNSEEN", mark_seen=False)))

            logger.debug(f"Folder {folder}: {total} total, {unread} unread")
            return (total, unread)

        except Exception as e:
            logger.error(f"Error getting message counts: {e}")
            raise EmailConnectionError(f"Failed to get message counts: {e}") from e

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False
