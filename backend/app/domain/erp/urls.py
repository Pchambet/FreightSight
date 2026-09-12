"""Deep links into a customer's Odoo web client."""

from urllib.parse import quote


def browser_base_url(url: str) -> str:
    """URL the user's browser can open.

    The API often reaches Odoo via ``host.docker.internal`` while the person demos on
    ``localhost`` — same port, different hostname.
    """
    return url.rstrip("/").replace("host.docker.internal", "localhost")


def odoo_record_url(url: str, database: str, model: str, record_id: int) -> str:
    """Open one Odoo record in the classic web client."""
    base = browser_base_url(url)
    db = quote(database, safe="")
    m = quote(model, safe="")
    return f"{base}/web?db={db}#id={record_id}&model={m}"
