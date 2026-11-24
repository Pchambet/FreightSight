"""What a file wrote: an import keeps the rows it created, so that any file can be taken back.

Only a costs file could be taken back, because only a cost names the import it came from. A person
who drops the wrong price list, the wrong orders or the wrong tracking sheet had no way back short of
deleting each row by hand. Every import now keeps the ids of the rows it created, by table.

NULL is a file committed before this was kept: nothing says what it wrote, so it cannot be taken back.

Revision ID: 0035
Revises: 0034
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("import_jobs", sa.Column("created", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("import_jobs", "created")
