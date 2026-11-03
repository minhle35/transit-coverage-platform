"""Feed version metadata loader: records GTFS download metadata to ops.feed_version.

Each load of GTFS data creates one feed_version row, keyed by SHA-256 of the
ZIP. This makes the load idempotent: re-running with the same data does not
create a second version record.

ops.active_version is a singleton that points to which feed_version is currently
serving; promotion and rollback are single UPDATEs here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.ops import ActiveVersion, FeedVersion


def extract_metadata(feed_version_id: str, source_url: str, row_counts: dict) -> dict:
    """Prepare feed version metadata for insertion.

    Args:
        feed_version_id: SHA-256 hash of the GTFS ZIP file
        source_url: URL where the feed was downloaded from
        row_counts: Dict of {table_name: row_count} from load
    """
    return {
        "feed_version_id": feed_version_id,
        "source_url": source_url,
        "sha256": feed_version_id,  # Redundant but matches schema
        "status": "loaded",
        "downloaded_at": datetime.now(timezone.utc),
        "row_counts": row_counts,
    }


def load_feed_version(metadata: dict, session: Session, set_active: bool = True) -> str:
    """Upsert feed_version row and optionally set as active.

    Args:
        metadata: Dict from extract_metadata()
        session: SQLAlchemy session
        set_active: If True, update ops.active_version to point to this feed

    Returns:
        feed_version_id for use in subsequent operations
    """
    feed_version_id = metadata["feed_version_id"]

    # Upsert feed_version: if same SHA exists, update metadata
    stmt = pg_insert(FeedVersion).values(metadata)
    update_cols = {
        c: stmt.excluded[c] for c in metadata if c not in ("feed_version_id", "sha256")
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=["sha256"],
        set_=update_cols,
    )
    session.execute(stmt)

    if set_active:
        # Ensure active_version row exists (upsert the singleton)
        active_stmt = pg_insert(ActiveVersion).values(
            id=1, feed_version_id=feed_version_id, model_run_id=None
        )
        active_stmt = active_stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={"feed_version_id": feed_version_id},
        )
        session.execute(active_stmt)

    session.commit()
    return feed_version_id
