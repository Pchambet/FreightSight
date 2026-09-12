"""Every table that carries an org_id is under Row Level Security, forced, with the tenant policy.

The per-table tests prove isolation for the tables someone thought of. This one is for the table
nobody thought of: a migration that adds an org-scoped table and forgets the three statements
would leak across tenants silently, and only a test that asks the catalogue can notice.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

#: Tables whose org_id is deliberately not the tenant boundary. Each one needs a reason.
EXEMPT: dict[str, str] = {
    # Read by primary key (org, user) while resolving the caller, before any tenant is known — a
    # policy keyed on the tenant setting would refuse the very lookup that establishes it. No API
    # endpoint reads or lists it; verified when this test was written (app/core/auth.py only).
    "memberships": "resolved before the tenant setting exists; only ever read by primary key",
}


def test_every_org_scoped_table_is_under_forced_rls_with_the_tenant_policy(db: Session) -> None:
    tables = [
        row[0]
        for row in db.execute(
            text(
                """
                SELECT c.relname
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE a.attname = 'org_id' AND NOT a.attisdropped
                  AND c.relkind = 'r' AND n.nspname = 'public'
                ORDER BY c.relname
                """
            )
        )
    ]
    assert tables, "no org-scoped table found: the query or the schema is wrong"

    missing: list[str] = []
    for table in tables:
        if table in EXEMPT:
            continue
        enabled, forced = db.execute(
            text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t"),
            {"t": table},
        ).one()
        policies = db.execute(
            text("SELECT count(*) FROM pg_policies WHERE tablename = :t AND policyname = 'tenant_isolation'"),
            {"t": table},
        ).scalar_one()
        if not (enabled and forced and policies == 1):
            missing.append(f"{table} (enabled={enabled}, forced={forced}, policy={policies})")
    assert not missing, "org-scoped tables without full RLS: " + ", ".join(missing)


def test_the_application_role_cannot_bypass_rls(db: Session) -> None:
    row = db.execute(
        text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'freightsight_app'")
    ).one_or_none()
    assert row is not None, "the application role is missing"
    assert row == (False, False)
