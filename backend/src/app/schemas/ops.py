"""Pydantic schemas for the `ops` endpoints.

These are *response* shapes, not tables. They exist so the API can promise a
stable JSON contract even when the database columns change underneath.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FeedVersionOut(BaseModel):
    # from_attributes lets FastAPI build this straight from a SQLAlchemy row.
    model_config = ConfigDict(from_attributes=True)

    feed_version_id: str
    source_url: str
    sha256: str
    status: str
    downloaded_at: datetime
    row_counts: dict


class ActiveVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feed_version_id: str | None
    model_run_id: str | None
    updated_at: datetime
