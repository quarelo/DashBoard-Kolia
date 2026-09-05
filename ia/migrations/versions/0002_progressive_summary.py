"""progressive summary columns on meeting_analyses

Replaces the ad-hoc `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` block that
init_database() ran on every startup. Server defaults are what let these columns
be added to a table that already holds rows.

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = (
    sa.Column("summary_attempt_started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("summary_attempt_started_chunks", sa.Integer(), nullable=False,
              server_default="0"),
    sa.Column("summary_stage", sa.Text(), nullable=False, server_default="PRELIMINARY"),
    sa.Column("summary_is_final", sa.Boolean(), nullable=False, server_default="false"),
)


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column("meeting_analyses", column.copy(), schema="ai")


def downgrade() -> None:
    for column in reversed(COLUMNS):
        op.drop_column("meeting_analyses", column.name, schema="ai")
