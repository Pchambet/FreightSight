"""`python -m app.backup` — the nightly dump. One Railway cron service runs this."""

from __future__ import annotations

import logging
import sys

from app.ops.backup import BackupError, run

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> int:
    try:
        result = run()
    except BackupError as exc:
        # A backup that fails silently is worse than none: say what is wrong, exit non-zero, and let
        # the scheduler's own alerting see it.
        print(f"backup failed: {exc}", file=sys.stderr)
        return 1
    print(f"backup written to {result.key} ({result.size_bytes} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
