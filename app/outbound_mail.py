from __future__ import annotations

import smtplib
import socket
import ssl
from email.message import EmailMessage
from pathlib import Path

import dns.resolver
import dkim

from app.config import settings


def smtp_relay_enabled() -> bool:
    return bool(settings.smtp_out_host and settings.smtp_out_from_email)


def direct_mx_enabled() -> bool:
    return bool(settings.direct_send_enabled and settings.direct_helo_host and settings.dkim_selector and settings.dkim_private_key_path)


def send_outbound_email(sender_email: str, recipients: list[str], subject: str, text_body: str, html_body: str) -> None:
    if smtp_relay_enabled():
        send_via_smtp_relay(sender_email, recipients, subject, text_body, html_body)
        return
    if direct_mx_enabled():
        send_via_direct_mx(sender_email, recipients, subject, text_body, html_body)
        return
    raise RuntimeError("no outbound delivery method is configured")


def build_message(sender_email: str, recipients: list[str], subject: str, text_body: str, html_body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = settings.smtp_out_from_email or sender_email
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message["Reply-To"] = sender_email

    if html_body and text_body:
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")
    elif html_body:
        message.set_content(html_body, subtype="html")
    else:
        message.set_content(text_body or "")
    return message


def send_via_smtp_relay(sender_email: str, recipients: list[str], subject: str, text_body: str, html_body: str) -> None:
    message = build_message(sender_email, recipients, subject, text_body, html_body)

    if settings.smtp_out_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_out_host, settings.smtp_out_port, timeout=30, context=ssl.create_default_context()) as server:
            if settings.smtp_out_username:
                server.login(settings.smtp_out_username, settings.smtp_out_password)
            server.send_message(message)
        return

    with smtplib.SMTP(settings.smtp_out_host, settings.smtp_out_port, timeout=30) as server:
        server.ehlo()
        if settings.smtp_out_use_tls:
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        if settings.smtp_out_username:
            server.login(settings.smtp_out_username, settings.smtp_out_password)
        server.send_message(message)


def send_via_direct_mx(sender_email: str, recipients: list[str], subject: str, text_body: str, html_body: str) -> None:
    for recipient in recipients:
        domain = recipient.rsplit("@", 1)[-1].strip().lower()
        hosts = resolve_mx_hosts(domain)
        if not hosts:
            raise RuntimeError(f"no mx records for {domain}")
        message = build_message(sender_email, [recipient], subject, text_body, html_body)
        signed_bytes = sign_message(message, sender_email)
        last_error: Exception | None = None
        for host in hosts:
            try:
                deliver_to_mx(host, sender_email, recipient, signed_bytes)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error


def resolve_mx_hosts(domain: str) -> list[str]:
    answers = dns.resolver.resolve(domain, "MX")
    records = sorted((record.preference, str(record.exchange).rstrip(".")) for record in answers)
    return [host for _, host in records]


def sign_message(message: EmailMessage, sender_email: str) -> bytes:
    private_key = Path(settings.dkim_private_key_path).read_bytes()
    sender_domain = sender_email.rsplit("@", 1)[-1].encode("utf-8")
    selector = settings.dkim_selector.encode("utf-8")
    raw = message.as_bytes()
    signature = dkim.sign(
        raw,
        selector=selector,
        domain=sender_domain,
        privkey=private_key,
        include_headers=[b"from", b"to", b"subject", b"reply-to"],
        canonicalize=(b"relaxed", b"relaxed"),
    )
    return signature + raw


def deliver_to_mx(host: str, sender_email: str, recipient: str, message_bytes: bytes) -> None:
    with smtplib.SMTP(host, 25, local_hostname=settings.direct_helo_host, timeout=60) as server:
        server.ehlo(settings.direct_helo_host)
        if server.has_extn("starttls"):
            server.starttls(context=ssl.create_default_context())
            server.ehlo(settings.direct_helo_host)
        refused = server.sendmail(sender_email, [recipient], message_bytes)
        if refused:
            raise RuntimeError(f"recipient refused: {refused}")


def can_connect_direct_mx(domain: str) -> tuple[bool, str]:
    hosts = resolve_mx_hosts(domain)
    if not hosts:
        return False, f"no mx records for {domain}"
    host = hosts[0]
    try:
        with socket.create_connection((host, 25), timeout=10):
            return True, host
    except Exception as exc:
        return False, f"{host}: {exc}"
