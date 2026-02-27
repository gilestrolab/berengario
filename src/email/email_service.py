"""
Email service daemon for continuous inbox monitoring.

This module provides a background service that polls the email inbox at
regular intervals, processes new messages, and handles graceful shutdown.
Includes exponential backoff on failures and comprehensive logging.
"""

import logging
import signal
import sys
import time
from datetime import datetime
from typing import Optional

from src.config import settings
from src.email.email_processor import EmailProcessor

logger = logging.getLogger(__name__)


class EmailService:
    """
    Background service for email inbox monitoring.

    This service continuously polls the email inbox at configured intervals,
    processes new messages, and handles graceful shutdown on termination signals.

    Attributes:
        processor: EmailProcessor instance for message handling
        check_interval: Seconds between inbox checks (from settings)
        running: Flag indicating if service is running
        failure_count: Count of consecutive failures
        max_failures: Maximum failures before extended backoff
    """

    def __init__(
        self,
        processor: Optional[EmailProcessor] = None,
        check_interval: Optional[int] = None,
    ):
        """
        Initialize email service.

        Args:
            processor: EmailProcessor instance (defaults to new instance)
            check_interval: Seconds between checks (defaults to settings)
        """
        self.processor = processor or EmailProcessor()
        self.check_interval = check_interval or settings.email_check_interval
        self.running = False
        self.failure_count = 0
        self.max_failures = 5

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        logger.info(
            f"EmailService initialized: check_interval={self.check_interval}s, "
            f"target={settings.email_target_address}"
        )

    def _signal_handler(self, signum, frame):
        """
        Handle shutdown signals.

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        signal_name = signal.Signals(signum).name
        logger.info(f"Received {signal_name}, initiating graceful shutdown...")
        self.stop()

    def _calculate_backoff_delay(self) -> int:
        """
        Calculate exponential backoff delay based on failure count.

        Returns:
            Delay in seconds (max 300s = 5 minutes).
        """
        if self.failure_count == 0:
            return self.check_interval

        # Exponential backoff: 2^(failures) * check_interval, capped at 300s
        delay = min(300, (2**self.failure_count) * self.check_interval)
        return delay

    def _process_inbox(self) -> bool:
        """
        Process inbox once.

        Returns:
            True if successful, False if errors occurred.
        """
        try:
            logger.debug("Checking inbox for new messages...")

            # Process unread emails
            results = self.processor.process_all_unread()

            if results:
                logger.info(
                    f"Processed {len(results)} messages: "
                    f"{sum(1 for r in results if r.success)} successful, "
                    f"{sum(1 for r in results if not r.success)} failed"
                )
            else:
                logger.debug("No new messages found")

            # Reset failure count on success
            self.failure_count = 0
            return True

        except Exception as e:
            logger.error(f"Error processing inbox: {e}", exc_info=True)
            self.failure_count += 1

            if self.failure_count >= self.max_failures:
                logger.warning(
                    f"Reached {self.max_failures} consecutive failures, "
                    f"entering extended backoff mode"
                )

            return False

    def start(self):
        """
        Start the email service daemon.

        Runs continuously until stopped, polling inbox at regular intervals.
        Implements exponential backoff on failures.
        """
        if self.running:
            logger.warning("Service is already running")
            return

        logger.info("=" * 60)
        logger.info(f"Starting EmailService - {datetime.now().isoformat()}")
        logger.info("=" * 60)
        logger.info(f"Instance: {settings.instance_name}")
        logger.info(f"Target: {settings.email_target_address}")
        logger.info(f"Check interval: {self.check_interval}s")
        logger.info(f"IMAP server: {settings.imap_server}:{settings.imap_port}")
        logger.info("=" * 60)

        self.running = True
        self.failure_count = 0

        # Initial inbox check
        logger.info("Performing initial inbox check...")
        self._process_inbox()

        # Main service loop
        while self.running:
            try:
                # Calculate sleep time (with backoff if failures)
                sleep_time = self._calculate_backoff_delay()

                if self.failure_count > 0:
                    logger.info(
                        f"Waiting {sleep_time}s before retry "
                        f"(failure count: {self.failure_count})"
                    )
                else:
                    logger.debug(f"Waiting {sleep_time}s until next check...")

                # Sleep in 1-second intervals to allow quick shutdown
                for _ in range(sleep_time):
                    if not self.running:
                        break
                    time.sleep(1)

                if not self.running:
                    break

                # Reload whitelists to pick up any changes made via admin interface
                try:
                    self.processor.reload_whitelists()
                except Exception as e:
                    logger.warning(f"Failed to reload whitelists: {e}")

                # Process inbox
                self._process_inbox()

            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, shutting down...")
                self.running = False
                break

            except Exception as e:
                logger.error(f"Unexpected error in service loop: {e}", exc_info=True)
                self.failure_count += 1
                time.sleep(5)  # Brief pause before retry

        logger.info("EmailService stopped")

    def stop(self):
        """
        Stop the email service daemon.

        Sets running flag to False, allowing the main loop to exit gracefully.
        """
        if not self.running:
            logger.warning("Service is not running")
            return

        logger.info("Stopping EmailService...")
        self.running = False

    def is_running(self) -> bool:
        """
        Check if service is running.

        Returns:
            True if service is running, False otherwise.
        """
        return self.running

    def get_status(self) -> dict:
        """
        Get service status information.

        Returns:
            Dictionary with service status metrics.
        """
        return {
            "running": self.running,
            "check_interval": self.check_interval,
            "failure_count": self.failure_count,
            "target_address": settings.email_target_address,
            "imap_server": settings.imap_server,
            "instance_name": settings.instance_name,
        }


def main():
    """
    Main entry point for email service daemon.

    Creates and starts the email service, running until interrupted.
    """
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(settings.log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )

    logger.info("=" * 60)
    logger.info("Berengario Email Service Daemon")
    logger.info("=" * 60)

    # Create and start service
    service = EmailService()

    try:
        service.start()
    except Exception as e:
        logger.error(f"Fatal error in email service: {e}", exc_info=True)
        sys.exit(1)

    logger.info("Email service daemon exited cleanly")
    sys.exit(0)


if __name__ == "__main__":
    main()
