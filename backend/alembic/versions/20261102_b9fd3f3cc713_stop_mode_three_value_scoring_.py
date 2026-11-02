"""stop mode: three-value scoring vocabulary, part of PK

Revision ID: b9fd3f3cc713
Revises: 2841096a513b
Create Date: 2026-11-02 19:52:19.076348

Three changes to core.stop.mode, all following README 5.2:

1. Vocabulary. The column held operational-branch labels ("Metropolitan
   Train", "SkyBus") which restate `zone` in English and carry no information
   it lacks. It now holds the scoring modes README 4.6 parameterises --
   rail, tram, bus -- grouped by right-of-way. Regional coach collapses into
   bus: street-running, same 400 m catchment. Existing rows are remapped
   rather than discarded.

2. Primary key. (feed_version_id, stop_id) is not unique over the feed. 60
   stop_ids serve two modes (40 tram+bus, 20 rail+bus) because Transport
   Victoria publishes one feed per operational branch. README 4.2's unit of
   analysis is the stop-mode pair, so the key becomes
   (feed_version_id, stop_id, mode). The loader separately collapses rows that
   are the same stop-mode pair published in several branches -- all measured at
   0 m apart -- see app/loaders/gtfs.py::_dedupe_stop_mode.

3. Constraint. mode is now NOT NULL (a key column) and checked against the
   three permitted values. A null mode would score as unreachable rather than
   failing loudly.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b9fd3f3cc713"
down_revision: Union[str, Sequence[str], None] = "2841096a513b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Operational branch -> scoring mode. Only needed to carry existing rows over;
# the loader derives this from the zone folder going forward.
BRANCH_TO_MODE = {
    "Regional Train": "rail",
    "Metropolitan Train": "rail",
    "Interstate": "rail",
    "Metropolitan Tram": "tram",
    "Myki Bus": "bus",
    "Regional Bus": "bus",
    "Regional Coach": "bus",
    "SkyBus": "bus",
}


def upgrade() -> None:
    """Upgrade schema."""
    # Remap before narrowing the column: the old labels are up to 18 characters
    # and would not survive the cast to VARCHAR(8).
    for branch, mode in BRANCH_TO_MODE.items():
        op.execute(
            sa.text("UPDATE core.stop SET mode = :mode WHERE mode = :branch").bindparams(
                mode=mode, branch=branch
            )
        )
    # Anything still unmapped cannot satisfy the new NOT NULL or CHECK. Fail
    # here with a clear message rather than deep inside the ALTER.
    op.execute(
        """
        DO $$
        DECLARE bad int;
        BEGIN
            SELECT count(*) INTO bad
            FROM core.stop
            WHERE mode IS NULL OR mode NOT IN ('rail', 'tram', 'bus');
            IF bad > 0 THEN
                RAISE EXCEPTION
                    'core.stop has % rows whose mode is null or outside '
                    '(rail, tram, bus). Remap them or reload the feed.', bad;
            END IF;
        END $$;
        """
    )

    op.alter_column(
        "stop",
        "mode",
        existing_type=sa.VARCHAR(length=30),
        type_=sa.String(length=8),
        nullable=False,
        schema="core",
    )
    op.drop_constraint("pk_stop", "stop", type_="primary", schema="core")
    op.create_primary_key(
        "pk_stop", "stop", ["feed_version_id", "stop_id", "mode"], schema="core"
    )
    op.create_check_constraint(
        "mode_valid", "stop", "mode IN ('rail', 'tram', 'bus')", schema="core"
    )


def downgrade() -> None:
    """Downgrade schema.

    Lossy in two ways, both unavoidable.

    The branch label a row came from is not recoverable from `mode` alone --
    "bus" could have been any of four branches -- so rows keep their
    scoring-mode values. Reload the feed to repopulate branch labels.

    More importantly, the narrower key cannot hold the 60 stop_ids that serve
    two modes, so one row per such stop is dropped, preferring rail over tram
    over bus. That discards real service, which is precisely why the key was
    widened. Reload after downgrading.
    """
    op.execute(
        """
        DELETE FROM core.stop s
        USING core.stop keep
        WHERE s.feed_version_id = keep.feed_version_id
          AND s.stop_id = keep.stop_id
          AND s.ctid <> keep.ctid
          AND array_position(ARRAY['rail','tram','bus'], keep.mode)
            < array_position(ARRAY['rail','tram','bus'], s.mode);
        """
    )
    op.drop_constraint("ck_stop_mode_valid", "stop", type_="check", schema="core")
    op.drop_constraint("pk_stop", "stop", type_="primary", schema="core")
    op.create_primary_key(
        "pk_stop", "stop", ["feed_version_id", "stop_id"], schema="core"
    )
    op.alter_column(
        "stop",
        "mode",
        existing_type=sa.String(length=8),
        type_=sa.VARCHAR(length=30),
        nullable=True,
        schema="core",
    )
