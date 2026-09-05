"""meeting versioning: a corrected transcription becomes a new version

Replaces infra/postgres/migrations/001_meeting_versions.sql. Re-importing a known
external_id with different text used to return 409 MEETING_CONFLICT, which left no
way to ingest a corrected transcript at all. It now writes a new version, so the
superseded row keeps its own analysis, chunks and citations.

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

OLD_UNIQUE_COLUMNS = ["external_id", "owner_id"]  # sorted, as pg_constraint reports them
NEW_UNIQUE = "meetings_owner_external_version_key"


def _unique_constraint_over(columns: list[str]) -> str | None:
    """Find a unique constraint by the columns it covers, not by its name.

    A database built by create_all() carries an auto-generated constraint name that
    differs from one built by migration 0001, so dropping it by a fixed name would
    work on one and silently miss on the other.
    """
    return op.get_bind().execute(sa.text("""
        SELECT con.conname
        FROM pg_constraint con
        WHERE con.conrelid = 'core.meetings'::regclass
          AND con.contype = 'u'
          AND (
              SELECT array_agg(att.attname::text ORDER BY att.attname::text)
              FROM unnest(con.conkey) AS k(attnum)
              JOIN pg_attribute att
                ON att.attrelid = con.conrelid AND att.attnum = k.attnum
          ) = :columns
    """), {"columns": columns}).scalar()


def upgrade() -> None:
    # Existing rows become version 1 through the server default, with no UPDATE.
    op.add_column("meetings",
                  sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
                  schema="core")
    op.add_column("meeting_imports",
                  sa.Column("versioned_count", sa.Integer(), nullable=False,
                            server_default="0"),
                  schema="core")

    # This is the constraint a second version has to violate, so it has to go first.
    existing = _unique_constraint_over(OLD_UNIQUE_COLUMNS)
    if existing:
        op.drop_constraint(existing, "meetings", schema="core", type_="unique")
    op.create_unique_constraint(
        NEW_UNIQUE, "meetings", ["owner_id", "external_id", "version"], schema="core")


def downgrade() -> None:
    # Collapsing versions would have to discard rows, so refuse instead of guessing
    # which version of a meeting the operator meant to keep.
    duplicates = op.get_bind().execute(sa.text("""
        SELECT count(*) FROM (
            SELECT 1 FROM core.meetings
            GROUP BY owner_id, external_id HAVING count(*) > 1
        ) AS d
    """)).scalar()
    if duplicates:
        raise RuntimeError(
            f"{duplicates} reunião(ões) têm mais de uma versão. "
            "Remova as versões extras antes de reverter esta migração."
        )
    op.drop_constraint(NEW_UNIQUE, "meetings", schema="core", type_="unique")
    op.create_unique_constraint(
        "meetings_owner_external_key", "meetings", ["owner_id", "external_id"],
        schema="core")
    op.drop_column("meeting_imports", "versioned_count", schema="core")
    op.drop_column("meetings", "version", schema="core")
