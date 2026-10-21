"""Email delivery service using standard library smtplib and email.message."""
from email.message import EmailMessage
import logging
import smtplib
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("pulse.email")
logger.setLevel(logging.INFO)


def _send_smtp_email(to_email: str, subject: str, plain_text: str, html_body: str) -> bool:
    """Shared helper for sending emails via SMTP or logging in dev mode."""
    if not settings.smtp_host or not settings.smtp_host.strip():
        # When SMTP_HOST is empty, only log in dev mode (never log passwords, tokens or links)
        logger.info(f"[DEV MODE] Email to {to_email} | Subject: '{subject}'")
        return True

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.effective_smtp_from
        msg["To"] = to_email
        msg.set_content(plain_text)
        msg.add_alternative(html_body, subtype="html")

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)

        logger.info(f"Email '{subject}' successfully sent to {to_email}")
        return True
    except Exception as exc:
        logger.error(f"Failed to send email '{subject}' to {to_email}: {type(exc).__name__}: {str(exc)}")
        return False


def send_password_reset_email(to_email: str, reset_link: str) -> bool:
    """Send a password reset email via SMTP or log to console in dev mode."""
    subject = "PULSE - Password Reset Link"
    plain_text = (
        f"Hello,\n\n"
        f"A password reset was requested for your PULSE account.\n\n"
        f"Use the following link to choose a new password:\n"
        f"{reset_link}\n\n"
        f"This link expires in 30 minutes.\n\n"
        f"If you did not make this request, you can safely ignore this email.\n\n"
        f"- The PULSE Ergonomics Team\n"
    )

    html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; line-height: 1.6; padding: 24px;">
  <h2 style="color: #4f46e5; margin-top: 0;">PULSE Password Reset</h2>
  <p>A password reset was requested for your PULSE account.</p>
  <p>Click the button below to choose a new password. This link is valid for 30 minutes:</p>
  <div style="margin: 28px 0;">
    <a href="{reset_link}" style="background-color: #4f46e5; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; display: inline-block;">Reset Password</a>
  </div>
  <p style="font-size: 13px; color: #64748b;">Or copy and paste this link into your browser:<br><a href="{reset_link}" style="color: #4f46e5;">{reset_link}</a></p>
  <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 30px 0;">
  <p style="font-size: 12px; color: #94a3b8;">If you did not request a password reset, you can safely ignore this email.</p>
</body>
</html>"""

    return _send_smtp_email(to_email, subject, plain_text, html_body)


def send_welcome_email(to_email: str, display_name: Optional[str] = None) -> bool:
    """Send a welcome confirmation email to newly registered users."""
    subject = "Welcome to PULSE"
    greeting = f"Hello {display_name}," if display_name and display_name.strip() else "Hello,"
    login_url = settings.app_base_url.rstrip("/")

    plain_text = (
        f"{greeting}\n\n"
        f"Welcome to PULSE! Your account was created with this email ({to_email}) and you can log in at {login_url}.\n\n"
        f"If you did not sign up, you can ignore this email.\n\n"
        f"- The PULSE Ergonomics Team\n"
    )

    html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; line-height: 1.6; padding: 24px;">
  <h2 style="color: #4f46e5; margin-top: 0;">Welcome to PULSE</h2>
  <p>{greeting}</p>
  <p>Your account was created with this email (<strong>{to_email}</strong>) and you can now log in at <a href="{login_url}" style="color: #4f46e5;">{login_url}</a>.</p>
  <p>Track your desk posture in real time and see your ergonomics score improve.</p>
  <div style="margin: 28px 0;">
    <a href="{login_url}" style="background-color: #4f46e5; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; display: inline-block;">Log In to PULSE</a>
  </div>
  <p style="font-size: 13px; color: #64748b;">Or visit your dashboard directly:<br><a href="{login_url}" style="color: #4f46e5;">{login_url}</a></p>
  <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 30px 0;">
  <p style="font-size: 12px; color: #94a3b8;">If you did not sign up, you can ignore this email.</p>
</body>
</html>"""

    return _send_smtp_email(to_email, subject, plain_text, html_body)

