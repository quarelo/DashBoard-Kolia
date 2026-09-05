"""initial schema: users, meeting imports and meetings

This is the shape the database had *before* meeting versioning. A database that
predates Alembic already looks exactly like this, so it can be adopted with
`alembic stamp 0001` instead of being rebuilt.

Revision ID: 0001
Revises:
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS core")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("role", sa.Enum("SALES_DIRECTOR", "USER", name="roleenum"),
                  nullable=False),
        sa.Column("password", sa.String(), nullable=False),
        schema="core",
    )
    # UserModel declares email as unique=True *and* index=True, which SQLAlchemy
    # renders as a single unique index rather than a constraint plus an index.
    op.create_index("ix_core_users_email", "users", ["email"], unique=True, schema="core")
    op.create_index("ix_core_users_id", "users", ["id"], schema="core")

    op.create_table(
        "meeting_imports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("core.users.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        # Re-uploading the same bytes, or the same records in another order, is a
        # duplicate for that owner; the constraints back up the service-level check.
        sa.UniqueConstraint("owner_id", "file_hash"),
        sa.UniqueConstraint("owner_id", "content_hash"),
        schema="core",
    )
    op.create_index("ix_core_meeting_imports_owner_id", "meeting_imports",
                    ["owner_id"], schema="core")

    op.create_table(
        "meetings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("core.users.id"), nullable=False),
        sa.Column("import_id", sa.Uuid(), sa.ForeignKey("core.meeting_imports.id"),
                  nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("transcription", sa.Text(), nullable=False),
        sa.Column("transcription_hash", sa.String(64), nullable=False),
        sa.Column("source_metadata", JSONB(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("owner_id", "external_id",
                            name="meetings_owner_external_key"),
        schema="core",
    )
    op.create_index("ix_core_meetings_owner_id", "meetings", ["owner_id"], schema="core")
    op.create_index("ix_core_meetings_import_id", "meetings", ["import_id"], schema="core")


def downgrade() -> None:
    op.drop_table("meetings", schema="core")
    op.drop_table("meeting_imports", schema="core")
    op.drop_table("users", schema="core")
    sa.Enum(name="roleenum").drop(op.get_bind(), checkfirst=True)
