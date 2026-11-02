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


class Route(Base):
    __tablename__ = "route"
    __table_args__ = {"schema": "core"}

    feed_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    route_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    agency_id: Mapped[str | None] = mapped_column(String(64))
    short_name: Mapped[str | None] = mapped_column(String(128))
    long_name: Mapped[str | None] = mapped_column(String(256))
    # GTFS route_type, kept verbatim. Victorian feeds use extended values
    # (400 = rail, 700 = bus, 900 = tram), so do not cast to the basic enum.
    route_type: Mapped[int] = mapped_column(Integer)
    # Derived in the loader: rail | tram | bus | coach.
    mode: Mapped[str] = mapped_column(String(16))


class Trip(Base):
    __tablename__ = "trip"
    __table_args__ = (
        Index("ix_trip_route", "feed_version_id", "route_id"),
        Index("ix_trip_service", "feed_version_id", "service_id"),
        {"schema": "core"},
    )

    feed_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trip_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    route_id: Mapped[str] = mapped_column(String(128))
    service_id: Mapped[str] = mapped_column(String(64))
    direction_id: Mapped[int | None] = mapped_column(SmallInteger)
    shape_id: Mapped[str | None] = mapped_column(String(64))


class ServiceCalendar(Base):
    """The weekly pattern. `start_date`/`end_date` are the validity window, not
    the service days — a calendar row can cover months."""

    __tablename__ = "service_calendar"
    __table_args__ = {"schema": "core"}

    feed_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    service_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    monday: Mapped[bool] = mapped_column(Boolean)
    tuesday: Mapped[bool] = mapped_column(Boolean)
    wednesday: Mapped[bool] = mapped_column(Boolean)
    thursday: Mapped[bool] = mapped_column(Boolean)
    friday: Mapped[bool] = mapped_column(Boolean)
    saturday: Mapped[bool] = mapped_column(Boolean)
    sunday: Mapped[bool] = mapped_column(Boolean)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)


class ServiceException(Base):
    """Calendar exceptions. exception_type 1 = service added, 2 = removed."""

    __tablename__ = "service_exception"
    __table_args__ = (
        CheckConstraint("exception_type IN (1, 2)", name="exception_type_valid"),
        {"schema": "core"},
    )

    feed_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    service_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    exception_type: Mapped[int] = mapped_column(SmallInteger)


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
