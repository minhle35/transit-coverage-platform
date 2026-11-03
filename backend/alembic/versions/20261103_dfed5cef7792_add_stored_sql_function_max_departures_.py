"""add_stored_sql_function_max_departures_in_catchment

Revision ID: dfed5cef7792
Revises: a2e03bae6e8c
Create Date: 2026-11-03 23:23:19.484220

"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "dfed5cef7792"
down_revision: Union[str, Sequence[str], None] = "a2e03bae6e8c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sql_path = (
        Path(__file__).parent.parent.parent
        / "sql"
        / "stored_functions"
        / "max_departures_in_catchment.sql"
    )
    sql_code = sql_path.read_text(encoding="utf-8")
    op.execute(sql_code)


def downgrade() -> None:
    """Remove max_departures_in_catchment function from core schema."""
    op.execute("""
        DROP FUNCTION IF EXISTS core.max_departures_in_catchment(
            GEOMETRY, FLOAT, VARCHAR, VARCHAR, VARCHAR, SMALLINT
        );
    """)
