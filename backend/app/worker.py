"""The worker process: `python -m app.worker`.

Same image and same environment as the API — it needs DATABASE_URL and nothing else that the API does
not already need. Concurrency and the queues to watch are environment-tunable so the Railway service
can be adjusted without a deploy.
"""

from __future__ import annotations

import logging
import os

from app.core.observability import configure_logging, init_sentry
from app.core.settings import get_settings
from app.jobs.app import get_app


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    init_sentry(settings)  # the worker is where the silent failures live: it has no user watching
    queues = [q.strip() for q in os.environ.get("WORKER_QUEUES", "").split(",") if q.strip()]
    concurrency = int(os.environ.get("WORKER_CONCURRENCY", "2"))
    logging.getLogger("freightsight.worker").info(
        "starting worker env=%s queues=%s concurrency=%s",
        settings.app_env,
        queues or "all",
        concurrency,
    )
    get_app().run_worker(queues=queues or None, concurrency=concurrency, install_signal_handlers=True)


if __name__ == "__main__":
    main()
