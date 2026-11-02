"""Conformed GTFS entities.

One module per source system. This one covers the schedule feed: stops, routes,
trips, the service calendar and the hourly departure aggregate.

Nothing here stores `stop_times`. That file is 650 MB in the bus feed; the
loader streams it and writes only `stop_service_hourly`. The original ZIP plus
its SHA-256 (in ops.feed_version) is the replayable raw layer.
"""

from __future__ import annotations

from datetime import date

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    Index,
    Integer,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Stop(Base):
    """A stop, platform, station, entrance or node.

    Victorian metro feeds publish all four. `location_type` follows GTFS:
    0/blank = platform, 1 = station, 2 = entrance, 3 = generic node.
    Only platforms and stations carry service, so `is_platform` and
    `is_station` are materialised here instead of being recomputed in SQL.
    """

    __tablename__ = "stop"
    __table_args__ = (
        Index("ix_stop_geom", "geom", postgresql_using="gist"),
        {"schema": "core"},
    )

    feed_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stop_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stop_code: Mapped[float | None] = mapped_column(Float)
    stop_name: Mapped[str | None] = mapped_column(String(256))
    stop_lat: Mapped[float | None] = mapped_column(Float)
    stop_lon: Mapped[float | None] = mapped_column(Float)
    location_type: Mapped[int] = mapped_column(SmallInteger, default=0)
    parent_station: Mapped[str | None] = mapped_column(String(64))
    wheelchair_boarding: Mapped[float | None] = mapped_column(Float, default=0)
    zone: Mapped[str | None] = mapped_column(String)
    platform_code: Mapped[str | None] = mapped_column(String(32))
    level_id: Mapped[str | None] = mapped_column(String)

    is_station: Mapped[bool] = mapped_column(Boolean, default=False)
    is_platform: Mapped[bool] = mapped_column(Boolean, default=False)

    # Metres, for every distance calculation. Never measure in 4326.
    geom: Mapped[object | None] = mapped_column(
        Geometry("POINT", srid=7899, spatial_index=False)
    )
    # Degrees, for GeoJSON and vector tiles at the edge.
    geom_4326: Mapped[object | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False)
    )


class StopServiceHourly(Base):
    """The only departure data the platform keeps.

    One row per stop, hour and day type. `stop_times` is streamed and discarded
    because the feed is large and the score only needs frequency.
    """

    __tablename__ = "stop_service_hourly"
    __table_args__ = (
        CheckConstraint("hour BETWEEN 0 AND 23", name="hour_range"),
        CheckConstraint(
            "day_type IN ('weekday', 'saturday', 'sunday')", name="day_type_valid"
        ),
        {"schema": "core"},
    )

    feed_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stop_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    day_type: Mapped[str] = mapped_column(String(8), primary_key=True)
    hour: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    departures: Mapped[int] = mapped_column(Integer)
