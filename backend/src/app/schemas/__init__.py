"""Pydantic schemas (API input and output).

Naming note: these are *not* Postgres schemas. Postgres schemas are the
DB_SCHEMAS tuple in app.models.base. The two words collide in this project, so
keep them straight:

    app.schemas   -> Pydantic models, what the API sends and accepts
    DB_SCHEMAS    -> raw, staging, core, marts, ops, api (inside Postgres)
"""

from app.schemas.health import HealthOut
from app.schemas.ops import ActiveVersionOut, FeedVersionOut

__all__ = [
    "ActiveVersionOut",
    "FeedVersionOut",
    "HealthOut",
]
