"""SQLAlchemy models.

Rule: every model module must be imported here.

Alembic compares Base.metadata against the database. A model that is never
imported never registers with Base.metadata, so autogenerate silently ignores
it — the table simply never appears in a migration. This file is the list of
what exists.
"""

from app.models.base import DB_SCHEMAS, Base
from app.models.ops import ActiveVersion, FeedVersion

__all__ = [
    "DB_SCHEMAS",
    "ActiveVersion",
    "Base",
    "FeedVersion",
]
