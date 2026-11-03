"""Shared pytest fixtures for loader tests."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.loaders.db import SessionLocal


@pytest.fixture
def session() -> Session:
    """Provide a database session for tests.

    Uses the same database as configured in app.config.Settings, so
    running tests requires the database to be up. Tests that require
    a session should mark themselves with @pytest.mark.db or handle
    the database dependency explicitly.
    """
    session = SessionLocal()
    try:
        yield session
        session.rollback()  # Never commit test changes
    finally:
        session.close()
