from email import policy
from email.parser import BytesParser

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import Envelope, Session

from app.config import settings
from app.crud import save_incoming_message
from app.database import Base, SessionLocal, engine
from app.utils import is_allowed_domain, normalize_address, split_address


def _extract_bodies(raw_content: bytes, max_chars: int) -> tuple[str | None, str | None, str]:
    message = BytesParser(policy=policy.default).parsebytes(raw_content)
    text_body: str | None = None
    html_body: str | None = None

    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            if part.get_content_disposition() == "attachment":
                continue
            payload = part.get_content()
            if isinstance(payload, bytes):
                payload = payload.decode(errors="replace")
            if not isinstance(payload, str):
                continue
            if content_type == "text/plain" and text_body is None:
                text_body = payload[:max_chars]
            if content_type == "text/html" and html_body is None:
                html_body = payload[:max_chars]
    else:
        payload = message.get_content()
        if isinstance(payload, bytes):
            payload = payload.decode(errors="replace")
        if isinstance(payload, str):
            if message.get_content_type() == "text/html":
                html_body = payload[:max_chars]
            else:
                text_body = payload[:max_chars]

    raw_headers = str(message)[:max_chars]
    return text_body, html_body, raw_headers


class TempMailSMTPHandler:
    async def handle_RCPT(self, server, session: Session, envelope: Envelope, address: str, rcpt_options):
        address = normalize_address(address)
        try:
            _, domain = split_address(address)
        except ValueError:
            return "550 invalid recipient"
        if not is_allowed_domain(domain):
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
            for recipient in envelope.rcpt_tos:
                save_incoming_message(
                    db,
                    recipient=recipient,
                    from_addr=from_addr,
                    subject=subject,
                    text_body=text_body,
                    html_body=html_body,
                    raw_headers=raw_headers,
                )
        finally:
            db.close()

        return "250 Message accepted for delivery"


def run_smtp_server() -> None:
    Base.metadata.create_all(bind=engine)
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
