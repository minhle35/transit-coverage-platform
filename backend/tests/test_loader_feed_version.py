"""Tests for app.loaders.feed_version."""

import pytest
from app.loaders.feed_version import extract_metadata, load_feed_version
from app.models.ops import FeedVersion, ActiveVersion
from sqlalchemy.orm import Session


@pytest.fixture
def sample_feed_id():
    """Sample SHA-256 feed version ID."""
    return "a3f42c1e8b9d7e6f5c4b3a2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3"


@pytest.fixture
def sample_row_counts():
    """Sample row counts from a load."""
    return {"core.stop": 31438, "core.area_sa1": 15478}


def test_extract_metadata_creates_dict(sample_feed_id, sample_row_counts):
    """extract_metadata returns a properly structured dict."""
    source_url = "https://www.transport.vic.gov.au/gtfs/prod/google_transit.zip"
    metadata = extract_metadata(sample_feed_id, source_url, sample_row_counts)

    assert metadata["feed_version_id"] == sample_feed_id
    assert metadata["sha256"] == sample_feed_id
    assert metadata["source_url"] == source_url
    assert metadata["status"] == "loaded"
    assert metadata["row_counts"] == sample_row_counts
    assert "downloaded_at" in metadata


def test_extract_metadata_includes_timestamp(sample_feed_id):
    """downloaded_at is set to current time."""
    from datetime import datetime

    source_url = "https://example.com/feed.zip"
    metadata = extract_metadata(sample_feed_id, source_url, {})

    assert isinstance(metadata["downloaded_at"], datetime)


def test_load_feed_version_inserts_to_db(
    session: Session, sample_feed_id, sample_row_counts
):
    """load_feed_version inserts a FeedVersion row."""
    source_url = "https://www.transport.vic.gov.au/gtfs/prod/google_transit.zip"
    metadata = extract_metadata(sample_feed_id, source_url, sample_row_counts)

    returned_id = load_feed_version(metadata, session, set_active=False)

    assert returned_id == sample_feed_id

    # Verify row was inserted
    row = session.query(FeedVersion).filter_by(feed_version_id=sample_feed_id).first()
    assert row is not None
    assert row.sha256 == sample_feed_id
    assert row.source_url == source_url
    assert row.status == "loaded"
    assert row.row_counts == sample_row_counts


def test_load_feed_version_sets_active(
    session: Session, sample_feed_id, sample_row_counts
):
    """load_feed_version sets ops.active_version when set_active=True."""
    source_url = "https://www.transport.vic.gov.au/gtfs/prod/google_transit.zip"
    metadata = extract_metadata(sample_feed_id, source_url, sample_row_counts)

    load_feed_version(metadata, session, set_active=True)

    # Verify active_version was updated
    active = session.query(ActiveVersion).filter_by(id=1).first()
    assert active is not None
    assert active.feed_version_id == sample_feed_id


def test_load_feed_version_upsert_on_duplicate_sha(
    session: Session, sample_feed_id, sample_row_counts
):
    """Loading the same SHA-256 twice updates, not duplicates."""
    source_url = "https://www.transport.vic.gov.au/gtfs/prod/google_transit.zip"

    # First load
    metadata1 = extract_metadata(sample_feed_id, source_url, sample_row_counts)
    load_feed_version(metadata1, session, set_active=False)

    # Second load with same SHA, updated metadata
    updated_counts = {"core.stop": 32000, "core.area_sa1": 15478}
    metadata2 = extract_metadata(sample_feed_id, source_url, updated_counts)
    load_feed_version(metadata2, session, set_active=False)

    # Verify only one row exists
    rows = session.query(FeedVersion).filter_by(feed_version_id=sample_feed_id).all()
    assert len(rows) == 1
    assert rows[0].row_counts == updated_counts


def test_load_feed_version_multiple_versions(session: Session, sample_row_counts):
    """Multiple distinct feed versions can be stored."""
    feed_id_1 = "a3f42c1e8b9d7e6f5c4b3a2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3"
    feed_id_2 = "b4e53d2f9c8e8f7g6d5c4b3e2f1g0b9c8d7e6f5g4b3c1d0e9f8a7c6d5e4d2"

    source_url = "https://www.transport.vic.gov.au/gtfs/prod/google_transit.zip"

    # Load two distinct versions
    metadata1 = extract_metadata(feed_id_1, source_url, sample_row_counts)
    metadata2 = extract_metadata(feed_id_2, source_url, sample_row_counts)

    load_feed_version(metadata1, session, set_active=True)
    load_feed_version(metadata2, session, set_active=True)

    # Verify both rows exist
    rows = session.query(FeedVersion).all()
    assert len(rows) >= 2
    assert any(r.feed_version_id == feed_id_1 for r in rows)
    assert any(r.feed_version_id == feed_id_2 for r in rows)

    # Verify active_version points to the latest
    active = session.query(ActiveVersion).filter_by(id=1).first()
    assert active.feed_version_id == feed_id_2
