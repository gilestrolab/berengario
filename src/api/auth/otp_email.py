"""
Shared OTP email delivery helper.

Used by both the main auth router and the platform admin auth router.
"""

import logging

logger = logging.getLogger(__name__)


async def send_otp_email(
    email_sender,
    to_address: str,
    otp_code: str,
    instance_name: str,
    organization: str = "",
    admin_mode: bool = False,
):
    """
    Send an OTP login code via email.

    Args:
        email_sender: EmailSender instance (must have ``send_reply``).
        to_address: Recipient email address.
        otp_code: The one-time password to include.
        instance_name: Application instance name (e.g. "Berengario").
        organization: Organization name appended to the footer (optional).
        admin_mode: If True, use "Platform Admin" branding.
    """
    label = f"{instance_name} Platform Admin" if admin_mode else instance_name

    subject = f"{label} - Your Login Code"

    footer_parts = [f"---\n{label}"]
    if organization and not admin_mode:
        footer_parts.append(organization)
    footer = "\n".join(footer_parts)

    body = (
        f"Your one-time login code is:\n\n"
        f"{otp_code}\n\n"
        f"This code will expire in 5 minutes.\n\n"
        f"If you didn't request this code, please ignore this email.\n\n"
        f"{footer}"
    )

    try:
        email_sender.send_reply(
            to_address=to_address,
            subject=subject,
            body_text=body,
            body_html=None,
        )
        prefix = "Admin OTP" if admin_mode else "OTP"
        logger.info(f"{prefix} email sent to {to_address}")
    except Exception as e:
        prefix = "admin OTP" if admin_mode else "OTP"
        logger.error(f"Failed to send {prefix} email to {to_address}: {e}")
