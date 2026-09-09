"""The notification port: how an alert leaves the application.

Alerts are grouped before they are sent — one message per organization per round, never one per
alert — so the port takes a batch. A digest of four containers is one thing a person reads; four
e-mails in a minute is what makes people filter you into a folder.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.models import Alert


@dataclass(frozen=True)
class Notification:
    org_id: UUID
    org_name: str
    recipients: list[str]
    alerts: list[Alert]

    @property
    def subject(self) -> str:
        if len(self.alerts) == 1:
            return f"FreightSight: {self.alerts[0].title}"
        return f"FreightSight: {len(self.alerts)} alerts"

    def text(self) -> str:
        lines = [f"{self.org_name} — {len(self.alerts)} alert(s)", ""]
        for alert in self.alerts:
            lines.append(f"[{alert.severity.value.upper()}] {alert.title}")
            if alert.body:
                lines.append(f"    {alert.body}")
        lines += ["", "Open FreightSight to acknowledge these."]
        return "\n".join(lines)


@runtime_checkable
class Notifier(Protocol):
    name: str

    def send(self, notification: Notification) -> None:
        """Deliver the digest, or raise. Raising means the alerts stay unnotified and are retried."""
        ...


def make_notifier() -> Notifier:
    """The notifier this deployment can actually use: Resend when it has a key, the log otherwise."""
    from app.adapters.notifications.log_notifier import LogNotifier
    from app.adapters.notifications.resend import ResendNotifier
    from app.core.settings import get_settings

    settings = get_settings()
    if settings.resend_api_key and settings.alerts_from_email:
        return ResendNotifier(
            settings.resend_api_key, settings.alerts_from_email, base_url=settings.resend_base_url
        )
    return LogNotifier()
