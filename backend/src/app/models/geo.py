"""Reference geography: SA1 boundaries and 2021 Census population.

These two tables come from different vintages, and that is the point.

    core.area_sa1          ASGS Edition 4, 2026 boundaries
    core.census_sa1        2021 Census, SA1 codes from Edition 3

Only ~80% of 2021 SA1 codes exist unchanged in the 2026 edition. Joining them
directly silently drops 1.39 million people. `core.sa1_correspondence` is the
explicit bridge: it maps a 2021 code to one or more 2026 codes with a
population share. Scoring must join through it, and must fail its quality gate
if the matched population falls below a configured threshold.
"""

from __future__ import annotations

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint, Float, Index, Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AreaSa1(Base):
    """A Statistical Area Level 1 polygon, 2026 edition (EPSG:7844 source)."""

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


class CensusSa1(Base):
    """2021 Census G01 for Victoria, one row per SA1.

    Only total population is promoted to a column. The other ~50 age/sex
    columns stay in `payload` so they are queryable without a migration when
    the equity analysis needs them.
    """

    __tablename__ = "census_sa1"
    __table_args__ = {"schema": "core"}

    sa1_code: Mapped[str] = mapped_column(String(11), primary_key=True)
    census_year: Mapped[int] = mapped_column(SmallInteger, default=2021)
    population: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class Sa1Correspondence(Base):
    """ABS 2021 -> 2026 SA1 correspondence.

    A 2021 SA1 can split across several 2026 SA1s, so the key is the pair and
    `ratio` is the share of the 2021 population assigned to the 2026 area.
    Rows must sum to 1.0 per `sa1_code_2021`; the loader asserts that.
    """

    __tablename__ = "sa1_correspondence"
    __table_args__ = (
        CheckConstraint("ratio > 0 AND ratio <= 1", name="ratio_range"),
        {"schema": "core"},
    )

    sa1_code_2021: Mapped[str] = mapped_column(String(11), primary_key=True)
    sa1_code_2026: Mapped[str] = mapped_column(String(11), primary_key=True)
    ratio: Mapped[float] = mapped_column(Float)
