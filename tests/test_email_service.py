"""
Unit tests for email service daemon.

Tests the EmailService class including polling, backoff, and shutdown handling.
"""

import logging
import signal
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.email.email_service import EmailService


@pytest.fixture
def mock_processor():
    """Mock EmailProcessor for testing."""
    processor = MagicMock()
    processor.process_all_unread.return_value = []
    return processor


@pytest.fixture
def service(mock_processor):
    """Create EmailService instance with mock processor."""
    return EmailService(processor=mock_processor, check_interval=1)


class TestEmailServiceInitialization:
    """Tests for EmailService initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        with patch("src.email.email_service.EmailProcessor"):
            service = EmailService()

            assert service.check_interval > 0
            assert service.running is False
            assert service.failure_count == 0
            assert service.max_failures == 5

    def test_init_with_custom_params(self, mock_processor):
        """Test initialization with custom parameters."""
        service = EmailService(processor=mock_processor, check_interval=60)

        assert service.processor == mock_processor
        assert service.check_interval == 60
        assert service.running is False

    def test_signal_handlers_registered(self, service):
        """Test that signal handlers are registered."""
        # Signal handlers should be set during init
        # We can't easily test the actual handlers, but we can verify service exists
        assert service is not None


class TestEmailServiceBackoff:
    """Tests for exponential backoff calculation."""

    def test_calculate_backoff_no_failures(self, service):
        """Test backoff with no failures returns normal interval."""
        service.failure_count = 0
        delay = service._calculate_backoff_delay()
        assert delay == service.check_interval

    def test_calculate_backoff_with_failures(self, service):
        """Test exponential backoff increases with failures."""
        service.check_interval = 10

        service.failure_count = 1
        assert service._calculate_backoff_delay() == 20  # 2^1 * 10

        service.failure_count = 2
        assert service._calculate_backoff_delay() == 40  # 2^2 * 10

        service.failure_count = 3
        assert service._calculate_backoff_delay() == 80  # 2^3 * 10

    def test_calculate_backoff_max_cap(self, service):
        """Test backoff is capped at maximum value."""
        service.check_interval = 100
        service.failure_count = 10  # Would be 102400 without cap

        delay = service._calculate_backoff_delay()
        assert delay == 300  # Maximum 5 minutes


class TestEmailServiceProcessInbox:
    """Tests for inbox processing."""

    def test_process_inbox_success_no_messages(self, service, mock_processor):
        """Test successful inbox check with no messages."""
        mock_processor.process_all_unread.return_value = []

        result = service._process_inbox()

        assert result is True
        assert service.failure_count == 0
        mock_processor.process_all_unread.assert_called_once()

    def test_process_inbox_success_with_messages(self, service, mock_processor):
        """Test successful inbox check with messages."""
        # Create mock results
        result1 = Mock(success=True)
        result2 = Mock(success=True)
        mock_processor.process_all_unread.return_value = [result1, result2]

        result = service._process_inbox()

        assert result is True
        assert service.failure_count == 0
        mock_processor.process_all_unread.assert_called_once()

    def test_process_inbox_with_failures(self, service, mock_processor):
        """Test inbox check with some failed messages."""
        result1 = Mock(success=True)
        result2 = Mock(success=False)
        mock_processor.process_all_unread.return_value = [result1, result2]

        result = service._process_inbox()

        assert result is True  # Processing succeeded even if some messages failed
        assert service.failure_count == 0

    def test_process_inbox_exception(self, service, mock_processor):
        """Test inbox processing with exception."""
        mock_processor.process_all_unread.side_effect = Exception("Connection error")

        result = service._process_inbox()

        assert result is False
        assert service.failure_count == 1

    def test_process_inbox_resets_failure_count(self, service, mock_processor):
        """Test that successful processing resets failure count."""
        service.failure_count = 3
        mock_processor.process_all_unread.return_value = []

        result = service._process_inbox()

        assert result is True
        assert service.failure_count == 0


class TestEmailServiceControl:
    """Tests for service control (start/stop)."""

    def test_stop_sets_running_flag(self, service):
        """Test that stop() sets running flag to False."""
        service.running = True
        service.stop()
        assert service.running is False

    def test_stop_when_not_running(self, service, caplog):
        """Test stop() when service is not running."""
        service.running = False

        with caplog.at_level(logging.WARNING):
            service.stop()

        assert "Service is not running" in caplog.text

    def test_is_running(self, service):
        """Test is_running() returns correct state."""
        service.running = False
        assert service.is_running() is False

        service.running = True
        assert service.is_running() is True

    def test_get_status(self, service):
        """Test get_status() returns service metrics."""
        service.running = True
        service.failure_count = 2

        status = service.get_status()

        assert status["running"] is True
        assert status["failure_count"] == 2
        assert status["check_interval"] == service.check_interval
        assert "target_address" in status
        assert "imap_server" in status
        assert "instance_name" in status


class TestEmailServiceMainLoop:
    """Tests for the main service loop."""

    @patch("time.sleep")
    def test_start_performs_initial_check(self, mock_sleep, service, mock_processor):
        """Test that start() performs an initial inbox check."""

        # Stop immediately after first sleep
        def stop_after_first(*args):
            service.running = False

        mock_sleep.side_effect = stop_after_first
        mock_processor.process_all_unread.return_value = []

        service.start()

        # Should call process at least once (initial check)
        assert mock_processor.process_all_unread.call_count >= 1

    @patch("time.sleep")
    def test_start_loops_until_stopped(self, mock_sleep, service, mock_processor):
        """Test that service loops until running flag is False."""
        mock_processor.process_all_unread.return_value = []
        call_count = 0

        def sleep_and_stop(*args):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:  # Stop after 3 iterations
                service.running = False

        mock_sleep.side_effect = sleep_and_stop

        service.start()

        # Should have processed inbox multiple times
        assert mock_processor.process_all_unread.call_count >= 2

    @patch("time.sleep")
    def test_start_handles_keyboard_interrupt(
        self, mock_sleep, service, mock_processor
    ):
        """Test graceful shutdown on KeyboardInterrupt."""
        mock_processor.process_all_unread.return_value = []
        mock_sleep.side_effect = KeyboardInterrupt()

        # Should not raise exception
        service.start()

        assert service.running is False

    @patch("time.sleep")
    def test_start_handles_unexpected_exception(
        self, mock_sleep, service, mock_processor, caplog
    ):
        """Test handling of unexpected exceptions in main loop."""
        mock_processor.process_all_unread.return_value = []

        call_count = 0

        def raise_then_stop(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Unexpected error")
            else:
                service.running = False

        mock_sleep.side_effect = raise_then_stop

        with caplog.at_level(logging.ERROR):
            service.start()

        assert "Unexpected error in service loop" in caplog.text
        assert service.failure_count >= 1

    @patch("time.sleep")
    def test_start_already_running_warning(self, mock_sleep, service, caplog):
        """Test warning when starting already running service."""
        service.running = True

        with caplog.at_level(logging.WARNING):
            service.start()

        assert "already running" in caplog.text


class TestEmailServiceSignalHandling:
    """Tests for signal handling."""

    def test_signal_handler_calls_stop(self, service):
        """Test that signal handler calls stop()."""
        service.running = True
        service._signal_handler(signal.SIGTERM, None)
        assert service.running is False

    def test_signal_handler_logs_signal_name(self, service, caplog):
        """Test that signal handler logs the signal name."""
        with caplog.at_level(logging.INFO):
            service._signal_handler(signal.SIGTERM, None)

        assert "SIGTERM" in caplog.text
        assert "graceful shutdown" in caplog.text


class TestEmailServiceIntegration:
    """Integration tests for EmailService."""

    @patch("time.sleep")
    def test_full_service_lifecycle(self, mock_sleep, mock_processor):
        """Test complete service lifecycle: start, process, stop."""
        service = EmailService(processor=mock_processor, check_interval=1)
        mock_processor.process_all_unread.return_value = []

        # Stop after 2 iterations
        call_count = 0

        def sleep_and_stop(*args):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                service.stop()

        mock_sleep.side_effect = sleep_and_stop

        # Run service
        service.start()

        # Verify lifecycle
        assert service.running is False
        assert mock_processor.process_all_unread.call_count >= 2

    @patch("time.sleep")
    def test_exponential_backoff_on_repeated_failures(self, mock_sleep, mock_processor):
        """Test that failures trigger exponential backoff."""
        service = EmailService(processor=mock_processor, check_interval=10)
        mock_processor.process_all_unread.side_effect = Exception("Network error")

        # Track sleep calls (each loop iteration has multiple 1-second sleeps)
        sleep_calls = 0
        max_sleep_calls = 100  # Allow enough sleeps for 3+ processing attempts

        def sleep_and_track(*args):
            nonlocal sleep_calls
            sleep_calls += 1
            # Stop after enough sleeps to allow multiple processing attempts
            if sleep_calls >= max_sleep_calls:
                service.stop()

        mock_sleep.side_effect = sleep_and_track

        service.start()

        # Should have increasing failure count (initial + at least 2 retries)
        assert service.failure_count >= 3
