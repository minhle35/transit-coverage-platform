"""Computed accessibility metrics: distance and coverage aggregations.

These tables materialize spatial query results so the API can serve them
without recomputing joins on every request. Idempotent: safe to recompute
with ON CONFLICT semantics.
"""

from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Sa1StopDistance(Base):
    """Closest stop of each mode to every SA1.

    One row per SA1-mode pair. Materialized from spatial join; versioned by feed.
    Geometries in metric (EPSG:7899) for distance accuracy and WGS84 (EPSG:4326) for API.
    """

    __tablename__ = "sa1_stop_distance"
    __table_args__ = (
        Index("ix_sa1_stop_distance_feed_sa1", "feed_version_id", "sa1_code"),
        Index("ix_sa1_stop_distance_distance", "feed_version_id", "distance_m"),
        Index("ix_sa1_stop_distance_geom", "geom", postgresql_using="gist"),
        {"schema": "core"},
    )

    feed_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ops.feed_version.feed_version_id"), primary_key=True
    )
    sa1_code: Mapped[str] = mapped_column(
        String(11), ForeignKey("core.area_sa1.sa1_code"), primary_key=True
    )
    mode: Mapped[str] = mapped_column(String(16), primary_key=True)
    closest_stop_id: Mapped[str | None] = mapped_column(String(64))
    distance_m: Mapped[float | None] = mapped_column(Float)
    stop_name: Mapped[str | None] = mapped_column(String(256))
    stop_lat: Mapped[float | None] = mapped_column(Float)
    stop_lon: Mapped[float | None] = mapped_column(Float)
    geom: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=7899), nullable=True
    )
    geom_4326: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Sa1Accessibility(Base):
    """Aggregated accessibility metrics per SA1.

    One row per SA1: distances to nearest stop by mode, stop counts in catchments,
    population-weighted frequency. Materialized for fast API queries.
    """

    __tablename__ = "sa1_accessibility"
    __table_args__ = (
        Index("ix_sa1_accessibility_feed", "feed_version_id"),
        Index("ix_sa1_accessibility_closest", "feed_version_id", "closest_stop_any_m"),
        Index("ix_sa1_accessibility_population", "feed_version_id", "population"),
        {"schema": "core"},
    )

    feed_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ops.feed_version.feed_version_id"), primary_key=True
    )
    sa1_code: Mapped[str] = mapped_column(
        String(11), ForeignKey("core.area_sa1.sa1_code"), primary_key=True
    )
    population: Mapped[int] = mapped_column(Integer, default=0)

    # Distance metrics (metres) by mode
    closest_stop_any_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    closest_rail_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    closest_tram_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    closest_bus_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    closest_coach_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Stop count metrics within catchments
    rail_within_800m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tram_within_400m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bus_within_400m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    coach_within_400m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stops_within_400m: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Frequency (max departures/hour across all stops within 400m catchment)
    max_deps_hr_400m: Mapped[int | None] = mapped_column(Integer, nullable=True)

    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
