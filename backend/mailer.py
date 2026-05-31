"""SMTP mail sender using aiosmtplib with admin-configured settings."""
import asyncio
from email.message import EmailMessage
import aiosmtplib


async def send_verification_email(
    settings: dict, to_email: str, verify_url: str
) -> bool:
    if not settings.get("smtp_enabled") or not settings.get("smtp_host"):
        return False
    msg = EmailMessage()
    msg["From"] = settings.get("smtp_from") or settings.get("smtp_user")
    msg["To"] = to_email
    msg["Subject"] = "Verify your StreamHub account"
    msg.set_content(
        f"Welcome to StreamHub!\n\nPlease verify your email by clicking the link below:\n\n{verify_url}\n\nIf you didn't sign up, ignore this email."
    )
    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.get("smtp_host"),
            port=int(settings.get("smtp_port", 587)),
            username=settings.get("smtp_user") or None,
            password=settings.get("smtp_password") or None,
            start_tls=bool(settings.get("smtp_use_tls", True)),
            timeout=15,
        )
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[mailer] failed: {e}")
        return False
