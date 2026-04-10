from email import policy
from email.message import Message
from email.parser import BytesParser

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import Envelope, Session

from app.config import settings
from app.mailer import send_via_smtp
from app.crud import configured_domains, get_app_settings, save_incoming_message
from app.database import SessionLocal, init_db
from app.utils import is_allowed_domain, normalize_address, split_address


def _decode_text_part(part: Message, max_chars: int) -> str | None:
    try:
        payload = part.get_payload(decode=True)
    except Exception:
        payload = None

    if payload is None:
        try:
            payload = part.get_payload()
        except Exception:
            return None

    if isinstance(payload, str):
        return payload[:max_chars]

    if not isinstance(payload, (bytes, bytearray)):
        return None

    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")[:max_chars]
    except LookupError:
        return payload.decode("utf-8", errors="replace")[:max_chars]


def _extract_bodies(raw_content: bytes, max_chars: int) -> tuple[str | None, str | None, str]:
    message = BytesParser(policy=policy.default).parsebytes(raw_content)
    text_body: str | None = None
    html_body: str | None = None

    for part in message.walk():
        if part.is_multipart():
            continue

        content_type = part.get_content_type()
        if part.get_content_disposition() == "attachment":
            continue

        payload = _decode_text_part(part, max_chars)
        if not payload:
            continue

        if content_type == "text/plain" and text_body is None:
            text_body = payload
        elif content_type == "text/html" and html_body is None:
            html_body = payload

    if text_body is None and html_body is None:
        fallback = _decode_text_part(message, max_chars)
        if message.get_content_type() == "text/html":
            html_body = fallback
        else:
            text_body = fallback

    raw_headers = str(message)[:max_chars]
    return text_body, html_body, raw_headers


def _split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _forward_targets(app_settings: dict, recipient_address: str) -> list[str]:
    if app_settings.get("forwardStatus", 1) != 0:
        return []
    recipients = _split_csv(app_settings.get("forwardEmail"))
    if not recipients:
        return []
    if app_settings.get("ruleType", 0) == 0:
        return recipients
    allowed_rules = {item.lower() for item in _split_csv(app_settings.get("ruleEmail"))}
    if recipient_address.lower() not in allowed_rules:
        return []
    return recipients


def _domain_allowed(app_settings: dict, domain: str) -> bool:
    normalized = domain.lower()
    for root in configured_domains(app_settings):
        if normalized == root or normalized.endswith(f".{root}"):
            return True
    return False


def _forward_message_if_needed(
    app_settings: dict,
    *,
    recipient_address: str,
    from_addr: str | None,
    subject: str | None,
    text_body: str | None,
    html_body: str | None,
) -> None:
    targets = _forward_targets(app_settings, recipient_address)
    if not targets:
        return
    smtp_host = (app_settings.get("smtpHost") or "").strip()
    if not smtp_host:
        return
    send_via_smtp(
        smtp_host=smtp_host,
        smtp_port=int(app_settings.get("smtpPort") or 587),
        smtp_username=(app_settings.get("smtpUsername") or "").strip() or None,
        smtp_password=app_settings.get("smtpPassword") or None,
        smtp_use_tls=bool(app_settings.get("smtpUseTls", True)),
        smtp_use_ssl=bool(app_settings.get("smtpUseSsl", False)),
        from_email=(app_settings.get("smtpFromEmail") or recipient_address).strip(),
        to_emails=targets,
        subject=subject or "",
        text_body=text_body,
        html_body=html_body,
        attachments=None,
    )


class TempMailSMTPHandler:
    async def handle_RCPT(self, server, session: Session, envelope: Envelope, address: str, rcpt_options):
        address = normalize_address(address)
        try:
            _, domain = split_address(address)
        except ValueError:
            return "550 invalid recipient"
        db = SessionLocal()
        try:
            app_settings = get_app_settings(db)
        finally:
            db.close()
        if app_settings.get("receive", 0) != 0:
            return "550 receive disabled"
        if not _domain_allowed(app_settings, domain):
            return "550 domain not allowed"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session: Session, envelope: Envelope):
        text_body, html_body, raw_headers = _extract_bodies(envelope.original_content, settings.max_body_chars)
        from_addr = normalize_address(envelope.mail_from) if envelope.mail_from else None
        subject = None

        try:
            parsed = BytesParser(policy=policy.default).parsebytes(envelope.original_content)
            subject = str(parsed.get("Subject", ""))[:998] or None
        except Exception:
            subject = None

        db = SessionLocal()
        try:
            app_settings = get_app_settings(db)
            for recipient in envelope.rcpt_tos:
                result = save_incoming_message(
                    db,
                    recipient=recipient,
                    from_addr=from_addr,
                    subject=subject,
                    text_body=text_body,
                    html_body=html_body,
                    raw_headers=raw_headers,
                )
                if result is not None:
                    try:
                        _forward_message_if_needed(
                            app_settings,
                            recipient_address=recipient,
                            from_addr=from_addr,
                            subject=subject,
                            text_body=text_body,
                            html_body=html_body,
                        )
                    except Exception as exc:
                        print(f"forward failed for {recipient}: {exc}")
        finally:
            db.close()

        return "250 Message accepted for delivery"


def run_smtp_server() -> None:
    init_db()
    controller = Controller(
        TempMailSMTPHandler(),
        hostname=settings.smtp_host,
        port=settings.smtp_port,
    )
    controller.start()
    print(f"SMTP server running at {settings.smtp_host}:{settings.smtp_port}")
    try:
        import time

        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        controller.stop()


if __name__ == "__main__":
    run_smtp_server()
