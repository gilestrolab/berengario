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
    Send an OTP login code via email (HTML + plain text).

    Args:
        email_sender: EmailSender instance (must have ``send_reply``).
        to_address: Recipient email address.
        otp_code: The one-time password to include.
        instance_name: Application instance name (e.g. "Berengario").
        organization: Organization name appended to the footer (optional).
        admin_mode: If True, use "Platform Admin" branding.
    """
    from src.email.email_sender import get_email_signature

    label = f"{instance_name} Platform Admin" if admin_mode else instance_name

    subject = f"{label} - Your Login Code"

    plain_sig, html_sig = get_email_signature(label)

    body_text = (
        f"Your one-time login code is:\n\n"
        f"{otp_code}\n\n"
        f"This code will expire in 5 minutes.\n\n"
        f"If you didn't request this code, please ignore this email.\n\n"
        f"{plain_sig}"
    )

    body_html = (
        f'<div style="font-family: Arial, Helvetica, sans-serif; line-height: 1.6; '
        f'color: #2E2E2E; max-width: 480px; margin: 0 auto; padding: 20px;">'
        f"<p>Your one-time login code is:</p>"
        f'<p style="font-size: 32px; font-weight: bold; letter-spacing: 6px; '
        f"color: #2A2520; text-align: center; margin: 24px 0; "
        f'padding: 16px; background: #F5F0EB; border-radius: 8px;">{otp_code}</p>'
        f'<p style="color: #8C8279; font-size: 13px;">'
        f"This code will expire in 5 minutes.</p>"
        f'<p style="color: #8C8279; font-size: 13px;">'
        f"If you didn't request this code, please ignore this email.</p>"
        f"{html_sig}"
        f"</div>"
    )

    try:
        email_sender.send_reply(
            to_address=to_address,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
        prefix = "Admin OTP" if admin_mode else "OTP"
        logger.info(f"{prefix} email sent to {to_address}")
    except Exception as e:
        prefix = "admin OTP" if admin_mode else "OTP"
        logger.error(f"Failed to send {prefix} email to {to_address}: {e}")
