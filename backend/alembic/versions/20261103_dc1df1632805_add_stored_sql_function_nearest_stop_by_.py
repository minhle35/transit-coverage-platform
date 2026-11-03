"""add nearest_stop_by_mode spatial function

Revision ID: dc1df1632805
Revises: bc33e4cdbabe
Create Date: 2026-11-03 22:12:53.886479

Implements STEP 4 Phase 1: first of three PostGIS spatial functions for proximity queries.
This function finds the single closest stop of a given mode to an origin point.

Design: stable, leakproof, uses GiST index on core.stop.geom via <-> operator.
See doc_PostGIS_Spatial_Core.md and plans.md Phase 1.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "dc1df1632805"
down_revision: Union[str, Sequence[str], None] = "bc33e4cdbabe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create nearest_stop_by_mode function in core schema."""
    # Read SQL from external file (relative to this migration file)
    sql_path = Path(__file__).parent.parent.parent / "sql" / "stored_functions" / "nearest_stop_by_mode.sql"
    sql_code = sql_path.read_text(encoding="utf-8")
    op.execute(sql_code)


def downgrade() -> None:
    """Remove nearest_stop_by_mode function from core schema."""
    op.execute("""
        DROP FUNCTION IF EXISTS core.nearest_stop_by_mode(
            GEOMETRY, VARCHAR, VARCHAR
        );
    """)
