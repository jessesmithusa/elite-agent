"""SMTP client for email sending."""

import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

from elite_agent.config import Config


def send_reply(
    cfg: Config,
    to_addr: str,
    subject: str,
    body: str,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    from_addr: Optional[str] = None,
) -> None:
    """Send an auto-reply email message.

    Sets threading headers (In-Reply-To, References) and auto-response markers
    (Auto-Submitted, X-Auto-Response-Suppress) to signal to receiving systems
    that this is an automated response.

    Args:
        cfg: Config object with smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from.
        to_addr: Recipient email address.
        subject: Email subject line.
        body: Email body text.
        in_reply_to: Optional Message-ID of the message being replied to.
        references: Optional References header value for threading.
        from_addr: Optional override for sender address (defaults to cfg.smtp_from).

    Raises:
        smtplib.SMTPException: If sending fails.
    """
    msg = EmailMessage()
    msg["From"] = from_addr or cfg.smtp_from
    msg["To"] = to_addr
    msg["Subject"] = subject

    # Threading headers for proper email client conversation threading
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    # Auto-response markers to signal this is an automated reply
    msg["Auto-Submitted"] = "auto-replied"
    msg["X-Auto-Response-Suppress"] = "All"

    msg.set_content(body)

    # Create SSL context and connect to SMTP server
    context = ssl.create_default_context()
    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        if cfg.smtp_user and cfg.smtp_pass:
            smtp.login(cfg.smtp_user, cfg.smtp_pass)
        smtp.send_message(msg)
