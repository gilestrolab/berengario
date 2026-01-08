"""
OTP (One-Time Password) management for authentication.

Handles OTP generation, verification, and lifecycle management.
"""

import logging
import secrets
from typing import Dict

from src.api.models import OTPEntry

logger = logging.getLogger(__name__)


class OTPManager:
    """
    Manages OTP generation, storage, and verification.

    Attributes:
        otps: Dictionary of email -> OTPEntry
    """

    def __init__(self):
        """Initialize OTP manager."""
        self.otps: Dict[str, OTPEntry] = {}
        logger.info("OTPManager initialized")

    def generate_otp(self, email: str) -> str:
        """
        Generate a new 6-digit OTP for email.

        Args:
            email: Email address

        Returns:
            6-digit OTP code
        """
        # Generate random 6-digit code
        code = "".join([str(secrets.randbelow(10)) for _ in range(6)])

        # Store OTP entry
        self.otps[email.lower()] = OTPEntry(code=code, email=email.lower())

        logger.info(f"Generated OTP for {email}")
        return code

    def verify_otp(self, email: str, code: str) -> tuple[bool, str]:
        """
        Verify OTP code for email.

        Args:
            email: Email address
            code: OTP code to verify

        Returns:
            Tuple of (success, message)
        """
        email = email.lower()

        # Check if OTP exists
        if email not in self.otps:
            return False, "No OTP found for this email. Please request a new one."

        otp_entry = self.otps[email]

        # Check if expired
        if otp_entry.is_expired():
            del self.otps[email]
            return False, "OTP has expired. Please request a new one."

        # Check if locked due to too many attempts
        if otp_entry.is_locked():
            del self.otps[email]
            return False, "Too many failed attempts. Please request a new OTP."

        # Increment attempts
        otp_entry.increment_attempts()

        # Verify code
        if otp_entry.code == code:
            # Success - remove OTP
            del self.otps[email]
            return True, "OTP verified successfully"
        else:
            remaining = otp_entry.max_attempts - otp_entry.attempts
            if remaining > 0:
                return False, f"Invalid OTP. {remaining} attempts remaining."
            else:
                del self.otps[email]
                return (
                    False,
                    "Invalid OTP. Maximum attempts reached. Please request a new one.",
                )

    def cleanup_expired(self):
        """Remove expired OTP entries."""
        expired = [email for email, otp in self.otps.items() if otp.is_expired()]
        for email in expired:
            del self.otps[email]
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired OTPs")
