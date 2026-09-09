"""Task declarations. Bodies live in `app/jobs/handlers.py` so the API can import names cheaply."""

from __future__ import annotations

from app.jobs.app import get_app

app = get_app()
