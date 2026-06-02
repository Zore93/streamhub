"""SMTP mail sender using aiosmtplib with admin-configured settings.

Supports BOTH common Gmail / Outlook setups:
- port 587 with STARTTLS upgrade (the default; "Use TLS = on")
- port 465 with implicit TLS (smtp_security="ssl" OR port == 465)
"""
from email.message import EmailMessage
import logging

import aiosmtplib

logger = logging.getLogger("streamhub.mailer")


def _normalize_password(pw: str | None) -> str | None:
    """Gmail App Passwords are displayed as `abcd efgh ijkl mnop` (with spaces).
    The actual password has no spaces — strip them so paste-from-Google works.
    """
    if pw is None:
        return None
    return pw.replace(" ", "").strip()


def _connection_kwargs(settings: dict) -> dict:
    """Choose start_tls vs use_tls vs plaintext based on settings + port.

    `smtp_security` (preferred):
        - "starttls"  → start_tls=True,  use_tls=False   (e.g. Gmail 587)
        - "ssl"       → start_tls=False, use_tls=True    (e.g. Gmail 465)
        - "none"      → start_tls=False, use_tls=False
    Fallback (legacy boolean): if `smtp_security` not set, infer from port +
    `smtp_use_tls`:
        - port 465  → ssl
        - smtp_use_tls=True  (default) → starttls
        - smtp_use_tls=False → none
    """
    port = int(settings.get("smtp_port", 587))
    sec = (settings.get("smtp_security") or "").lower().strip()
    if not sec:
        if port == 465:
            sec = "ssl"
        elif settings.get("smtp_use_tls", True):
            sec = "starttls"
        else:
            sec = "none"
    if sec == "ssl":
        return {"start_tls": False, "use_tls": True}
    if sec == "starttls":
        return {"start_tls": True, "use_tls": False}
    return {"start_tls": False, "use_tls": False}


async def _send(settings: dict, msg: EmailMessage) -> None:
    """Raise on failure so callers can surface the actual error to the UI."""
    if not settings.get("smtp_host"):
        raise RuntimeError("SMTP host not configured")
    await aiosmtplib.send(
        msg,
        hostname=settings.get("smtp_host"),
        port=int(settings.get("smtp_port", 587)),
        username=settings.get("smtp_user") or None,
        password=_normalize_password(settings.get("smtp_password")),
        timeout=20,
        **_connection_kwargs(settings),
    )


def _build(settings: dict, to_email: str, subject: str, body: str,
           reply_to: str | None = None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.get("smtp_from") or settings.get("smtp_user")
    msg["To"] = to_email
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    return msg


async def send_verification_email(settings: dict, to_email: str, verify_url: str) -> bool:
    """Returns True on success, False on (logged) failure — used during signup so
    a broken SMTP setup doesn't block registration entirely."""
    if not settings.get("smtp_enabled") or not settings.get("smtp_host"):
        return False
    msg = _build(
        settings, to_email,
        subject="Verify your StreamHub account",
        body=(
            "Welcome to StreamHub!\n\n"
            "Please verify your email by clicking the link below:\n\n"
            f"{verify_url}\n\n"
            "If you didn't sign up, ignore this email."
        ),
    )
    try:
        await _send(settings, msg)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("verification mail failed: %s", e)
        return False


async def send_test_email(settings: dict, to_email: str) -> None:
    """Like send_verification_email but RAISES on failure — used by the admin
    'Send test email' button to surface the exact SMTP error."""
    msg = _build(
        settings, to_email,
        subject="StreamHub SMTP test",
        body=(
            "Hello!\n\nThis is a test email from your StreamHub admin panel — "
            "if you're reading it, SMTP is correctly configured.\n"
        ),
    )
    await _send(settings, msg)


async def send_contact_message(settings: dict, to_email: str, sender_email: str,
                                title: str, message: str) -> None:
    """RAISES on failure so the /contact endpoint can return a real error."""
    msg = _build(
        settings, to_email,
        subject=f"[StreamHub Contact] {title}",
        body=f"From: {sender_email}\n\n{message}",
        reply_to=sender_email,
    )
    await _send(settings, msg)
