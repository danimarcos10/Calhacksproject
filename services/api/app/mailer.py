"""Send one coach email through the app's Gmail account."""

import html
import logging
import smtplib
from email.message import EmailMessage

from app.config import Settings
from app.errors import AppError

log = logging.getLogger("secondlook.mail")


def html_body(text: str) -> str:
    blocks: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        if _stat_line(lines[index]):
            rows: list[tuple[str, str]] = []
            while index < len(lines) and _stat_line(lines[index]):
                label, _, value = lines[index].partition(":")
                rows.append((label.strip(), value.strip()))
                index += 1
            table = "".join(
                f"<tr><td>{html.escape(label)}</td><td>{html.escape(value)}</td></tr>" for label, value in rows
            )
            blocks.append(f"<table>{table}</table>")
            continue
        paragraph: list[str] = []
        while index < len(lines) and lines[index].strip() and not _stat_line(lines[index]):
            paragraph.append(lines[index].strip())
            index += 1
        blocks.append(f"<p>{html.escape(' '.join(paragraph))}</p>")
    return "\n".join(blocks)


STAT_LABELS = {
    "seconds tracked",
    "receives",
    "passes",
    "carries",
    "ball losses",
    "actions a tracked minute",
    "clips analysed",
    "evidence confidence",
}


def _stat_line(line: str) -> bool:
    label, separator, value = line.partition(":")
    return bool(separator and value.strip() and label.strip().casefold() in STAT_LABELS)


def send(settings: Settings, to: str, subject: str, text: str, html_text: str, reply_to: str) -> str:
    if not settings.smtp_user.strip() or not settings.smtp_app_password.strip():
        raise AppError("mail_not_configured", "Mail is not connected on this server. Add the Gmail app password.", 503)
    delivered = to
    outbound = subject
    if not settings.mail_live:
        if not settings.mail_test_to.strip():
            raise AppError("mail_not_configured", "Set MAIL_TEST_TO to try a send. Live sending is off.", 503)
        delivered = settings.mail_test_to.strip()
        outbound = f"[Test for {to}] {subject}"
    message = EmailMessage()
    message["From"] = f"{settings.mail_from_name} <{settings.smtp_user.strip()}>"
    message["To"] = delivered
    message["Subject"] = outbound
    if reply_to.strip():
        message["Reply-To"] = reply_to.strip()
    message.set_content(text)
    message.add_alternative(html_text, subtype="html")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(settings.smtp_user.strip(), settings.smtp_app_password.strip())
            smtp.send_message(message)
    except smtplib.SMTPException:
        log.warning("smtp send failed")
        raise AppError("mail_failed", "The email could not be sent. Try again.", 502, retryable=True) from None
    return delivered
