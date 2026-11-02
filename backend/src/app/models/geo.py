"""Reference geography: SA1 boundaries.

SA1 is the finest Census geography with full population counts. Two editions are supported:
- 2021 (ASGS Edition 3): matches 2021 Census data exactly
- 2026 (ASGS Edition 4): newer edition, future-proofing for post-2026 Census
"""

from __future__ import annotations

from geoalchemy2 import Geometry
from sqlalchemy import Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AreaSa1(Base):
    """A Statistical Area Level 1 polygon.

    Supports both 2021 (ASGS Edition 3) and 2026 (ASGS Edition 4) editions.
    Geometries in metric (EPSG:7899) for distance queries and WGS84 (EPSG:4326) for GeoJSON.
    """

    __tablename__ = "area_sa1"
    __table_args__ = (
        Index("ix_area_sa1_geom", "geom", postgresql_using="gist"),
        Index("ix_area_sa1_gcc", "gcc_code"),
        {"schema": "core"},
    )

    sa1_code: Mapped[str] = mapped_column(String(11), primary_key=True)
    edition: Mapped[str] = mapped_column(String(4), default="2026")
    # Filled from the ABS correspondence table. NULL means "not yet matched",
    # which the scoring gate must treat as an error, not as zero population.
    sa1_code_2021: Mapped[str | None] = mapped_column(String(11), index=True)

    sa2_code: Mapped[str | None] = mapped_column(String(9))
    sa2_name: Mapped[str | None] = mapped_column(String(128))
    sa3_code: Mapped[str | None] = mapped_column(String(5))
    sa4_code: Mapped[str | None] = mapped_column(String(3))
    gcc_code: Mapped[str | None] = mapped_column(String(5))
    gcc_name: Mapped[str | None] = mapped_column(String(64))
    ste_code: Mapped[str | None] = mapped_column(String(1))

    area_sqm: Mapped[float | None] = mapped_column(Float)

    geom: Mapped[object | None] = mapped_column(
        Geometry("MULTIPOLYGON", srid=7899, spatial_index=False)
    )
    geom_4326: Mapped[object | None] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False)
    )
