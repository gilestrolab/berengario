"""
Unit tests for IMAP email client.

Tests email client connection, message fetching, and error handling.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from imap_tools import MailMessage
from imap_tools.errors import MailboxLoginError

from src.email.email_client import (
    EmailClient,
    EmailConnectionError,
    EmailAuthenticationError,
)


@pytest.fixture
def mock_settings():
    """Mock settings for email configuration."""
    with patch("src.email.email_client.settings") as mock:
        mock.imap_server = "imap.example.com"
        mock.imap_port = 993
        mock.imap_user = "test@example.com"
        mock.imap_password = "test_password"
        mock.imap_use_ssl = True
        yield mock


@pytest.fixture
def mock_mailbox():
    """Mock MailBox for testing."""
    with patch("src.email.email_client.MailBox") as MockMailBox:
        mock_instance = MagicMock()
        MockMailBox.return_value = mock_instance
        yield mock_instance


class TestEmailClient:
    """Tests for EmailClient class."""

    def test_init_with_defaults(self, mock_settings):
        """Test initializing client with default settings."""
        client = EmailClient()

        assert client.server == "imap.example.com"
        assert client.port == 993
        assert client.username == "test@example.com"
        assert client.password == "test_password"
        assert client.use_ssl is True

    def test_init_with_custom_params(self, mock_settings):
        """Test initializing client with custom parameters."""
        client = EmailClient(
            server="custom.server.com",
            port=143,
            username="custom@example.com",
            password="custom_pass",
            use_ssl=False,
        )

        assert client.server == "custom.server.com"
        assert client.port == 143
        assert client.username == "custom@example.com"
        assert client.password == "custom_pass"
        assert client.use_ssl is False

    def test_connect_success(self, mock_settings, mock_mailbox):
        """Test successful connection to IMAP server."""
        client = EmailClient()

        result = client.connect()

        assert result is True
        assert client.is_connected() is True
        mock_mailbox.login.assert_called_once_with("test@example.com", "test_password")

    def test_connect_already_connected(self, mock_settings, mock_mailbox):
        """Test connecting when already connected."""
        client = EmailClient()
        client.connect()

        # Try to connect again
        result = client.connect()

        assert result is True
        # Login should only be called once
        assert mock_mailbox.login.call_count == 1

    def test_connect_authentication_failure(self, mock_settings, mock_mailbox):
        """Test connection with authentication failure."""
        # Create proper MailboxLoginError with required arguments
        error = Exception("Invalid credentials")
        mock_mailbox.login.side_effect = error

        client = EmailClient()

        with pytest.raises(EmailConnectionError) as exc_info:
            client.connect()

        assert "Connection failed" in str(exc_info.value)
        assert client.is_connected() is False

    def test_connect_connection_failure(self, mock_settings):
        """Test connection failure."""
        with patch("src.email.email_client.MailBox") as MockMailBox:
            MockMailBox.side_effect = ConnectionError("Cannot reach server")

            client = EmailClient()

            with pytest.raises(EmailConnectionError) as exc_info:
                client.connect()

            assert "Connection failed" in str(exc_info.value)

    def test_disconnect(self, mock_settings, mock_mailbox):
        """Test disconnecting from server."""
        client = EmailClient()
        client.connect()

        client.disconnect()

        assert client.is_connected() is False
        mock_mailbox.logout.assert_called_once()

    def test_disconnect_when_not_connected(self, mock_settings):
        """Test disconnecting when not connected."""
        client = EmailClient()

        # Should not raise error
        client.disconnect()

        assert client.is_connected() is False

    def test_is_connected_when_connected(self, mock_settings, mock_mailbox):
        """Test is_connected returns True when connected."""
        mock_mailbox.client.noop.return_value = None

        client = EmailClient()
        client.connect()

        assert client.is_connected() is True
        mock_mailbox.client.noop.assert_called()

    def test_is_connected_when_not_connected(self, mock_settings):
        """Test is_connected returns False when not connected."""
        client = EmailClient()

        assert client.is_connected() is False

    def test_is_connected_health_check_fails(self, mock_settings, mock_mailbox):
        """Test is_connected when health check fails."""
        mock_mailbox.client.noop.side_effect = ConnectionError("Connection lost")

        client = EmailClient()
        client.connect()

        # First call succeeds (during connect)
        mock_mailbox.client.noop.side_effect = None
        assert client.is_connected() is True

        # Second call fails
        mock_mailbox.client.noop.side_effect = ConnectionError("Connection lost")
        assert client.is_connected() is False

    def test_reconnect_success(self, mock_settings, mock_mailbox):
        """Test successful reconnection."""
        client = EmailClient()
        client.connect()

        # Simulate connection loss
        client._connected = False

        with patch("time.sleep"):  # Skip delay in tests
            result = client.reconnect()

        assert result is True
        assert client.is_connected() is True

    def test_reconnect_exceeds_max_attempts(self, mock_settings, mock_mailbox):
        """Test reconnection fails after max attempts."""
        mock_mailbox.login.side_effect = ConnectionError("Cannot connect")

        client = EmailClient()
        client._reconnect_attempts = 3  # Already at max

        with patch("time.sleep"):
            result = client.reconnect()

        assert result is False

    def test_ensure_connected_when_connected(self, mock_settings, mock_mailbox):
        """Test ensure_connected when already connected."""
        client = EmailClient()
        client.connect()

        # Should not raise error
        client.ensure_connected()

        # Should not attempt reconnection
        assert mock_mailbox.login.call_count == 1

    def test_ensure_connected_reconnects(self, mock_settings, mock_mailbox):
        """Test ensure_connected reconnects when disconnected."""
        client = EmailClient()
        client.connect()

        # Simulate connection loss
        client._connected = False

        with patch("time.sleep"):
            client.ensure_connected()

        # Should have reconnected
        assert mock_mailbox.login.call_count == 2

    def test_fetch_unread_messages(self, mock_settings, mock_mailbox):
        """Test fetching unread messages."""
        # Create mock messages
        mock_msg1 = MagicMock(spec=MailMessage)
        mock_msg2 = MagicMock(spec=MailMessage)
        mock_mailbox.fetch.return_value = iter([mock_msg1, mock_msg2])

        client = EmailClient()
        client.connect()

        messages = client.fetch_unread()

        assert len(messages) == 2
        mock_mailbox.folder.set.assert_called_with("INBOX")
        mock_mailbox.fetch.assert_called_once()

    def test_fetch_unread_with_limit(self, mock_settings, mock_mailbox):
        """Test fetching unread messages with limit."""
        mock_msg = MagicMock(spec=MailMessage)
        mock_mailbox.fetch.return_value = iter([mock_msg])

        client = EmailClient()
        client.connect()

        messages = client.fetch_unread(limit=10)

        assert len(messages) == 1
        # Verify limit was passed to fetch
        call_kwargs = mock_mailbox.fetch.call_args[1]
        assert call_kwargs.get("limit") == 10

    def test_fetch_unread_from_custom_folder(self, mock_settings, mock_mailbox):
        """Test fetching from custom folder."""
        mock_mailbox.fetch.return_value = iter([])

        client = EmailClient()
        client.connect()

        client.fetch_unread(folder="Sent")

        mock_mailbox.folder.set.assert_called_with("Sent")

    def test_fetch_unread_not_connected(self, mock_settings, mock_mailbox):
        """Test fetching when not connected raises error."""
        mock_mailbox.client.noop.side_effect = ConnectionError("Not connected")
        mock_mailbox.login.side_effect = ConnectionError("Cannot connect")

        client = EmailClient()

        with pytest.raises(EmailConnectionError):
            client.fetch_unread()

    def test_mark_seen(self, mock_settings, mock_mailbox):
        """Test marking message as seen."""
        client = EmailClient()
        client.connect()

        result = client.mark_seen("12345")

        assert result is True
        mock_mailbox.flag.assert_called_once_with("12345", ["\\Seen"], True)

    def test_mark_unseen(self, mock_settings, mock_mailbox):
        """Test marking message as unseen."""
        client = EmailClient()
        client.connect()

        result = client.mark_unseen("12345")

        assert result is True
        mock_mailbox.flag.assert_called_once_with("12345", ["\\Seen"], False)

    def test_get_folder_list(self, mock_settings, mock_mailbox):
        """Test getting folder list."""
        mock_folder1 = MagicMock()
        mock_folder1.name = "INBOX"
        mock_folder2 = MagicMock()
        mock_folder2.name = "Sent"

        mock_mailbox.folder.list.return_value = [mock_folder1, mock_folder2]

        client = EmailClient()
        client.connect()

        folders = client.get_folder_list()

        assert folders == ["INBOX", "Sent"]

    def test_get_message_count(self, mock_settings, mock_mailbox):
        """Test getting message counts."""
        # Mock all messages
        all_msgs = [MagicMock() for _ in range(10)]
        # Mock unread messages
        unread_msgs = [MagicMock() for _ in range(3)]

        # Configure fetch to return different results based on criteria
        def fetch_side_effect(*args, **kwargs):
            criteria = kwargs.get("criteria", "")
            if criteria == "ALL":
                return iter(all_msgs)
            elif criteria == "UNSEEN":
                return iter(unread_msgs)
            return iter([])

        mock_mailbox.fetch.side_effect = fetch_side_effect

        client = EmailClient()
        client.connect()

        total, unread = client.get_message_count()

        assert total == 10
        assert unread == 3

    def test_context_manager(self, mock_settings, mock_mailbox):
        """Test using client as context manager."""
        with EmailClient() as client:
            assert client.is_connected() is True

        # Should be disconnected after context
        mock_mailbox.logout.assert_called_once()

    def test_context_manager_with_error(self, mock_settings, mock_mailbox):
        """Test context manager disconnects even on error."""
        with pytest.raises(ValueError):
            with EmailClient() as client:
                raise ValueError("Test error")

        # Should still disconnect
        mock_mailbox.logout.assert_called_once()
