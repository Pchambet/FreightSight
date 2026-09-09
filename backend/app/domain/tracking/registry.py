"""Which providers this deployment can talk to.

A provider is built from settings, so a missing credential is a configuration fact rather than a
crash: the Terminal49 adapter, for instance, verifies and parses webhooks with only its signing
secret, and refuses `subscribe` with a clear error until an API key exists.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.errors import NotFound
from app.core.settings import Settings, get_settings
from app.domain.tracking.manual import ManualProvider
from app.domain.tracking.ports import TrackingProvider

BUILDERS: dict[str, Callable[[Settings], TrackingProvider]] = {
    "manual": lambda _: ManualProvider(),
}


def get_provider(name: str, settings: Settings | None = None) -> TrackingProvider:
    builder = BUILDERS.get(name.lower())
    if builder is None:
        raise NotFound(f"Tracking provider {name!r}")
    return builder(settings or get_settings())


def provider_names() -> list[str]:
    return sorted(BUILDERS)
