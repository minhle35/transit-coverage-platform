"""Tables in the `ops` schema: pipeline and model metadata.

This is the only schema the API needs to read besides `api`, which is why it
is the first one modelled. Data tables (`core`, `marts`) come later, in their
own modules: core.py, marts.py.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FeedVersion(Base):
    """One archived GTFS download.

    The primary key is the file's SHA-256, so retrying the same download can
    never create a second version. That is what makes the load idempotent.
    """

    __tablename__ = "feed_version"
    __table_args__ = {"schema": "ops"}

    feed_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_url: Mapped[str] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    # downloaded -> validated -> loaded -> promoted | quarantined
    status: Mapped[str] = mapped_column(String(16), default="downloaded")
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    row_counts: Mapped[dict] = mapped_column(JSONB, default=dict)


class ActiveVersion(Base):
    """Exactly one row. Promotion and rollback are each a single UPDATE here,
    inside the same transaction that moves the data."""

    __tablename__ = "active_version"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        {"schema": "ops"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    feed_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("ops.feed_version.feed_version_id")
    )
    model_run_id: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
