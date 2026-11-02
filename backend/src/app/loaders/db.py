"""Shared engine and session factory. Every loader imports `get_session`
instead of building its own engine, so there is exactly one connection pool
and one place that reads Settings().db.database_url."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engine = create_engine(get_settings().db.database_url, future=True)
SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


@contextmanager
def get_session() -> Iterator[Session]:
    """One transaction per call: commits on success, rolls back on error.

    A loader's `load()` should do all its writes inside a single `with
    get_session()` block, so a failure partway through never leaves a
    half-written table -- the same delete-then-insert-in-a-transaction
    idea as the pipeline design, just scoped to one Python function.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
