import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.app.core.config import settings
from src.app.core.database import Base


class Product(Base):
    """One row per TOTVS catalogue product, loaded once by the scraper in ia/scraper/.

    Not written to by the analysis pipeline: this table is a read-only reference
    catalogue, populated out-of-band so a chunk's embedding can later be matched
    against real products instead of relying on the LLM to invent one.
    """
    __tablename__ = "products"
    __table_args__ = {"schema": "ai"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Unique, not just indexed: this is what makes a rerun of the loader safe to
    # skip duplicating a product instead of silently doubling every row.
    source_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # name + description, exactly what was embedded — kept for audit/debugging
    # without having to recompute it from the two fields above.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
