from __future__ import annotations

import time
from email import policy
from email.parser import BytesParser

import httpx
from aiosmtpd.controller import Controller

from app.config import settings


class MailHandler:
    async def handle_DATA(self, _server, _session, envelope):
        message = BytesParser(policy=policy.default).parsebytes(envelope.original_content)
        payload = {
            "from": envelope.mail_from,
            "to": list(envelope.rcpt_tos),
            "subject": message.get("subject", ""),
            "text": self._body_as_text(message),
            "html": self._body_as_html(message),
            "raw": envelope.original_content.decode("utf-8", errors="replace"),
        }

        headers = {
            "content-type": "application/json",
            "x-smtp-gateway-token": settings.smtp_gateway_token,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{settings.smtp_api_base}/internal/smtp/receive", json=payload, headers=headers)
            response.raise_for_status()
        return "250 Message accepted"

    @staticmethod
    def _body_as_text(message) -> str:
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == "text/plain":
                    return part.get_content()
        if message.get_content_type() == "text/plain":
            return message.get_content()
        return ""

    @staticmethod
    def _body_as_html(message) -> str:
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == "text/html":
                    return part.get_content()
        if message.get_content_type() == "text/html":
            return message.get_content()
        return ""


def main() -> None:
    controller = Controller(MailHandler(), hostname=settings.smtp_host, port=settings.smtp_port)
    controller.start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
