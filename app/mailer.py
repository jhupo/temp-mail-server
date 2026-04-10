from __future__ import annotations

import base64
import smtplib
from email.message import EmailMessage


def send_via_smtp(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str | None,
    smtp_password: str | None,
    smtp_use_tls: bool,
    smtp_use_ssl: bool,
    from_email: str,
    to_emails: list[str],
    subject: str,
    text_body: str | None,
    html_body: str | None,
    attachments: list[dict] | None = None,
) -> None:
    message = EmailMessage()
    message["From"] = from_email
    message["To"] = ", ".join(to_emails)
    message["Subject"] = subject

    plain_text = text_body or ""
    message.set_content(plain_text)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    for item in attachments or []:
        if not item.get("content") or not item.get("filename"):
            continue
        raw = item["content"]
        if isinstance(raw, str) and raw.startswith("data:") and ";base64," in raw:
            _header, raw = raw.split(",", 1)
        payload = base64.b64decode(raw)
        content_type = (item.get("contentType") or "application/octet-stream").split("/", 1)
        if len(content_type) != 2:
            maintype, subtype = "application", "octet-stream"
        else:
            maintype, subtype = content_type
        message.add_attachment(payload, maintype=maintype, subtype=subtype, filename=item["filename"])

    if smtp_use_ssl:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as client:
            if smtp_username:
                client.login(smtp_username, smtp_password or "")
            client.send_message(message)
        return

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as client:
        if smtp_use_tls:
            client.starttls()
        if smtp_username:
            client.login(smtp_username, smtp_password or "")
        client.send_message(message)
