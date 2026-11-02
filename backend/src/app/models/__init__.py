"""SQLAlchemy models.

Rule: every model module must be imported here.

Alembic compares Base.metadata against the database. A model that is never
imported never registers with Base.metadata, so autogenerate silently ignores
it — the table simply never appears in a migration. This file is the list of
what exists.
"""

from app.models.base import DB_SCHEMAS, Base
from app.models.geo import AreaSa1, CensusSa1, Sa1Correspondence
from app.models.gtfs import (
    Route,
    ServiceCalendar,
    ServiceException,
    Stop,
    StopServiceHourly,
    Trip,
)
from app.models.ops import ActiveVersion, FeedVersion

__all__ = [
    "Base",
    "DB_SCHEMAS",
    "ActiveVersion",
    "AreaSa1",
    "CensusSa1",
    "FeedVersion",
    "Route",
    "Sa1Correspondence",
    "ServiceCalendar",
    "ServiceException",
    "Stop",
    "StopServiceHourly",
    "Trip",
]
