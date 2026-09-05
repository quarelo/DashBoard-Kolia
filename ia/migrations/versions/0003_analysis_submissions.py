"""analysis_submissions: idempotency keys for /analisar

The key is claimed before the analysis is prepared, so a retry after a timeout
returns the original analysis instead of creating a second one. RESTRICT on the
foreign key stops an analysis from being deleted while a claim still points at it.

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_submissions",
        # The key is a lowercase SHA-256 hex digest, validated before insert.
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("analysis_id", UUID(as_uuid=True),
                  sa.ForeignKey("ai.meeting_analyses.id", ondelete="RESTRICT"),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        schema="ai",
    )


def downgrade() -> None:
    op.drop_table("analysis_submissions", schema="ai")
