import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.app.core.database import Base


class ScoringWeight(Base):
    """One motive's weight and its wording for the interface.

    The point tables used to be constants in `scoring_service.py`, so moving a
    weight meant a deploy — and the weights are exactly what the commercial team
    needs to turn while calibrating. The code is the key and never changes: it is
    written into every `chunk_summary` already stored, and renaming it would orphan
    those. The name and the description are what the screen shows, and they are
    editable.

    `ruler_version` is the same number on every row, bumped once per save. A score
    is stored with the version of the ruler that produced it, so two numbers on the
    dashboard can be told apart when the ruler moved between them.
    """

    __tablename__ = "scoring_weights"
    __table_args__ = (
        CheckConstraint("points between 0 and 100", name="scoring_weights_points_range"),
        CheckConstraint("side in ('CHURN', 'OPPORTUNITY')", name="scoring_weights_side"),
        {"schema": "ai"},
    )

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    side: Mapped[str] = mapped_column(Text, index=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    points: Mapped[int] = mapped_column(Integer)
    ruler_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[str | None] = mapped_column(Text, nullable=True)
