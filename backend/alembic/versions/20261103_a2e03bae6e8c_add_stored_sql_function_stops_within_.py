"""add_stored_sql_function_stops_within_radius

Revision ID: a2e03bae6e8c
Revises: dc1df1632805
Create Date: 2026-11-03 23:23:11.407700

"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a2e03bae6e8c"
down_revision: Union[str, Sequence[str], None] = "dc1df1632805"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    sql_path = (
        Path(__file__).parent.parent.parent
        / "sql"
        / "stored_functions"
        / "stops_within_radius.sql"
    )
    sql_code = sql_path.read_text(encoding="utf-8")
    op.execute(sql_code)


def downgrade() -> None:
    """Remove stops_within_radius function from core schema."""
    op.execute("""
        DROP FUNCTION IF EXISTS core.stops_within_radius(
            GEOMETRY, FLOAT, VARCHAR, VARCHAR
        );
    """)
