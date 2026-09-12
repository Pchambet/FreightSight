"""The alert in the reader's language, written from its kind and its payload.

This is `frontend/src/features/alerts/text.ts` done server-side, for the e-mail digest. The screen
already builds its sentence from the kind and the moving parts; a digest that kept the stored English
would have the same alert reading one way in the application and another way in the inbox. The
sentences here are the ones in `frontend/messages/{fr,en}.json`, and a test compares the two so they
cannot drift apart quietly.

The alert's own `title` and `body` stay English and stay the fallback: a kind this module does not
know, or a payload that lacks what a sentence needs — an alert raised before the payload carried it
— is sent as it was stored rather than as a half-written phrase.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from app.domain.models import Alert, AlertKind, AlertSeverity

#: French first: the product is sold to French importers. Same list as the front's i18n config.
LOCALES = ("fr", "en")
DEFAULT_LOCALE = "fr"

MESSAGES: dict[str, dict[str, str]] = {
    "fr": {
        "DND_RISK.title": "{container} : risque de surestaries {risk}",
        "DND_RISK.body": "Dernier jour franc le {lfd}.",
        "DND_RISK.bodyRunning": "Le dernier jour franc était le {lfd}. Les surestaries courent.",
        "DND_RISK.bodyLeft.one": "Dernier jour franc le {lfd}, {days} jour restant.",
        "DND_RISK.bodyLeft.other": "Dernier jour franc le {lfd}, {days} jours restants.",
        "DND_RISK.bodyNoLfd": "Dernier jour franc inconnu.",
        "ETA_CHANGED.title": "{container} : arrivée décalée de {hours} h {direction}",
        "ETA_CHANGED.later": "plus tard",
        "ETA_CHANGED.earlier": "plus tôt",
        "ETA_CHANGED.body": "Nouvelle ETA {eta}, au lieu de {previous}.",
        "ETA_CHANGED.bodyNoPrevious": "Nouvelle ETA {eta}.",
        "TRACKING_DATA_MISSING.title": "Aucune donnée de suivi pour {container}",
        "TRACKING_DATA_MISSING.body": (
            "{provider} n'a rien envoyé depuis au moins {hours} h. "
            "Vérifiez le conteneur sur le site du transporteur."
        ),
        "TRACKING_PROVIDER_DOWN.title": "{provider} ne répond pas",
        "TRACKING_PROVIDER_DOWN.body": (
            "Impossible de joindre {provider} pour plusieurs conteneurs d'affilée : les mises à jour "
            "de suivi sont en pause jusqu'à ce qu'il réponde. Les conteneurs eux-mêmes n'ont rien : "
            "rien à faire ici, le prochain passage reprendra où celui-ci s'est arrêté."
        ),
        "risk.NONE": "Aucun risque",
        "risk.LOW": "Faible",
        "risk.MEDIUM": "Moyen",
        "risk.HIGH": "Élevé",
        "risk.INCURRING": "Surestaries en cours",
        # The digest itself has no equivalent on the screen: nobody reads an e-mail there.
        "severity.info": "Info",
        "severity.warning": "Attention",
        "severity.critical": "Critique",
        "digest.subjectOne": "FreightSight : {title}",
        "digest.subjectMany": "FreightSight : {count} alertes",
        "digest.headingOne": "{org} — {count} alerte",
        "digest.headingMany": "{org} — {count} alertes",
        "digest.footer": "Ouvrez FreightSight pour les marquer comme lues.",
    },
    "en": {
        "DND_RISK.title": "{container}: demurrage risk {risk}",
        "DND_RISK.body": "Last free day {lfd}.",
        "DND_RISK.bodyRunning": "The last free day was {lfd}. Demurrage is running.",
        "DND_RISK.bodyLeft.one": "Last free day {lfd}, {days} day left.",
        "DND_RISK.bodyLeft.other": "Last free day {lfd}, {days} days left.",
        "DND_RISK.bodyNoLfd": "Last free day unknown.",
        "ETA_CHANGED.title": "{container}: arrival moved {hours} h {direction}",
        "ETA_CHANGED.later": "later",
        "ETA_CHANGED.earlier": "earlier",
        "ETA_CHANGED.body": "New ETA {eta}, was {previous}.",
        "ETA_CHANGED.bodyNoPrevious": "New ETA {eta}.",
        "TRACKING_DATA_MISSING.title": "No tracking data for {container}",
        "TRACKING_DATA_MISSING.body": (
            "{provider} has sent nothing for at least {hours} h. "
            "Check the container on the carrier's own site."
        ),
        "TRACKING_PROVIDER_DOWN.title": "{provider} is not answering",
        "TRACKING_PROVIDER_DOWN.body": (
            "We could not reach {provider} for several containers in a row, so tracking updates are "
            "paused until it answers again. Nothing is wrong with the containers themselves, and "
            "nothing needs doing here: the next round picks up where this one stopped."
        ),
        "risk.NONE": "No risk",
        "risk.LOW": "Low",
        "risk.MEDIUM": "Medium",
        "risk.HIGH": "High",
        "risk.INCURRING": "Incurring",
        "severity.info": "Info",
        "severity.warning": "Warning",
        "severity.critical": "Critical",
        "digest.subjectOne": "FreightSight: {title}",
        "digest.subjectMany": "FreightSight: {count} alerts",
        "digest.headingOne": "{org} — {count} alert",
        "digest.headingMany": "{org} — {count} alerts",
        "digest.footer": "Open FreightSight to acknowledge these.",
    },
}

#: Short month names for English dates, so the sentence does not depend on the process locale.
_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def normalise_locale(value: str | None) -> str:
    """The locale we speak that is closest to what was asked. `fr-CA` is French; `de` is not German."""
    if not value:
        return DEFAULT_LOCALE
    base = value.strip().lower().replace("_", "-").split("-")[0]
    return base if base in LOCALES else DEFAULT_LOCALE


def t(locale: str, key: str, **values: Any) -> str:
    template = MESSAGES[normalise_locale(locale)][key]
    return template.format(**values) if values else template


def severity_label(severity: AlertSeverity, locale: str) -> str:
    return t(locale, f"severity.{severity.value}")


def alert_text(
    alert: Alert,
    locale: str,
    *,
    container_number: str | None = None,
    now: datetime | None = None,
) -> tuple[str, str]:
    """The title and body to show a reader of `locale`, from the alert's kind and payload."""
    payload = alert.payload if isinstance(alert.payload, dict) else {}
    fallback = (alert.title, alert.body or "")
    container = container_number or ""

    if alert.kind is AlertKind.DND_RISK:
        risk = _str(payload, "risk")
        if not risk or not container:
            return fallback
        title = t(locale, "DND_RISK.title", container=container, risk=_risk_label(risk, locale))
        lfd = _date(_str(payload, "last_free_day"))
        if lfd is None:
            return title, t(locale, "DND_RISK.bodyNoLfd")
        printed = _format_date(lfd, locale)
        if risk == "INCURRING":
            return title, t(locale, "DND_RISK.bodyRunning", lfd=printed)
        today = (now or datetime.now(UTC)).date()
        days = (lfd - today).days
        if days < 0:
            return title, t(locale, "DND_RISK.body", lfd=printed)
        return title, t(locale, _plural(locale, "DND_RISK.bodyLeft", days), lfd=printed, days=days)

    if alert.kind is AlertKind.ETA_CHANGED:
        hours = _number(payload, "delta_hours")
        eta = _datetime(_str(payload, "eta"))
        if hours is None or eta is None or not container:
            return fallback
        direction = t(locale, "ETA_CHANGED.later" if hours > 0 else "ETA_CHANGED.earlier")
        title = t(
            locale,
            "ETA_CHANGED.title",
            container=container,
            hours=abs(round(hours)),
            direction=direction,
        )
        previous = _datetime(_str(payload, "previous_eta"))
        if previous is None:
            return title, t(locale, "ETA_CHANGED.bodyNoPrevious", eta=_format_datetime(eta, locale))
        return title, t(
            locale,
            "ETA_CHANGED.body",
            eta=_format_datetime(eta, locale),
            previous=_format_datetime(previous, locale),
        )

    if alert.kind is AlertKind.TRACKING_DATA_MISSING:
        provider = _str(payload, "provider")
        hours = _number(payload, "hours")
        if not provider or hours is None or not container:
            return fallback
        return (
            t(locale, "TRACKING_DATA_MISSING.title", container=container),
            t(locale, "TRACKING_DATA_MISSING.body", provider=provider, hours=round(hours)),
        )

    if alert.kind is AlertKind.TRACKING_PROVIDER_DOWN:
        provider = _str(payload, "provider")
        if not provider:
            return fallback
        return (
            t(locale, "TRACKING_PROVIDER_DOWN.title", provider=provider),
            t(locale, "TRACKING_PROVIDER_DOWN.body", provider=provider),
        )

    return fallback


def _risk_label(code: str, locale: str) -> str:
    key = f"risk.{code}"
    return MESSAGES[normalise_locale(locale)].get(key, code)


def _plural(locale: str, key: str, count: int) -> str:
    """French counts 0 and 1 as one; English counts only 1. Same rule as the ICU messages."""
    one = count == 1 or (normalise_locale(locale) == "fr" and count == 0)
    return f"{key}.one" if one else f"{key}.other"


def _str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def _number(payload: dict[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, bool):  # a bool is an int, and never a count of hours
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _format_date(value: date, locale: str) -> str:
    if normalise_locale(locale) == "fr":
        return f"{value.day:02d}/{value.month:02d}/{value.year}"
    return f"{value.day:02d} {_MONTHS_EN[value.month - 1]} {value.year}"


def _format_datetime(value: datetime, locale: str) -> str:
    """Always UTC, like the screen: an ETA read in two time zones is two different facts."""
    utc = value.astimezone(UTC)
    stamp = f"{utc.day:02d}/{utc.month:02d}/{utc.year} {utc.hour:02d}:{utc.minute:02d}"
    return stamp if normalise_locale(locale) == "fr" else stamp.replace(" ", ", ", 1)
