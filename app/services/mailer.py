"""Envio de e-mail. Em desenvolvimento (sem SMTP_HOST) os e-mails vão para o log."""

import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

from app.config import settings

log = logging.getLogger("running_control.mailer")


class EmailSender(Protocol):
    def send(self, to: list[str], subject: str, text: str, html: str) -> None: ...


class SmtpSender:
    def send(self, to: list[str], subject: str, text: str, html: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, ", ".join(to), subject
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)


class LogSender:
    def send(self, to: list[str], subject: str, text: str, html: str) -> None:
        log.warning("[e-mail não enviado — SMTP não configurado] para=%s assunto=%s\n%s", to, subject, text)


@dataclass
class MemorySender:
    """Usado nos testes: guarda os e-mails em memória."""

    sent: list[dict] = field(default_factory=list)

    def send(self, to: list[str], subject: str, text: str, html: str) -> None:
        self.sent.append({"to": to, "subject": subject, "text": text, "html": html})


def default_sender() -> EmailSender:
    return SmtpSender() if settings.smtp_host else LogSender()
