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
    """A GTFS stop, in one mode, for one feed version.

    **Grain:** one row per `(feed_version_id, stop_id, mode)`. Not one row per
    stop — `stop_id` is not unique across the feed, because Transport Victoria
    publishes one GTFS archive per operational branch and a stop served by two
    branches appears in both. README 4.2's unit of analysis is the stop-mode
    pair, so that is the key. A stop serving two modes (tram and bus, say) is
    two rows; a stop republished by two branches of the *same* mode is one,
    merged by the loader. See README 5.2 and 5.4 item 3.

    `location_type` follows GTFS: 0 = platform, 1 = station, 2 = entrance,
    3 = generic node. Only platforms and stations carry service (README 5.4
    item 4), so service queries filter `location_type IN (0, 1)` — entrances and
    nodes are kept for wayfinding and parent-station resolution, never scored.

    Coordinates are held only as geometry, never as loose latitude and
    longitude: `geom` in EPSG:7899 for every distance calculation, `geom_4326`
    in WGS84 for GeoJSON at the API edge (README 3.2).
    """

    __tablename__ = "stop"
    __table_args__ = (
        Index("ix_stop_geom", "geom", postgresql_using="gist"),
        {"schema": "core"},
    )

    feed_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stop_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Scoring mode, grouped by right-of-way. README 4.6 parameterises R_m and
    # w_m for exactly these three; the eight operational branches the feed is
    # published under are not modes and are not stored. See README 5.2.
    #
    # In the key because the grain is the stop-mode pair: 60 stop_ids in the
    # snapshot serve two modes (40 tram+bus, 20 rail+bus) and collapsing them
    # would drop one mode's service from the score.
    mode: Mapped[str] = mapped_column(
        String(8),
        CheckConstraint("mode IN ('rail', 'tram', 'bus')", name="mode_valid"),
        primary_key=True,
    )

    stop_name: Mapped[str | None] = mapped_column(String(256))
    location_type: Mapped[int] = mapped_column(SmallInteger, default=0)
    # The station a platform belongs to. Required by README 4.3: platforms under
    # one parent are merged per mode, so a twelve-platform interchange counts
    # once rather than twelve times. Without it every score near a large station
    # is inflated by its platform count.
    parent_station: Mapped[str | None] = mapped_column(String(64))
    # GTFS enum, not a measurement: 0 = no information, 1 = some accessible
    # boarding, 2 = not possible. Null in the feed means 0.
    wheelchair_boarding: Mapped[int] = mapped_column(SmallInteger, default=0)
    # Needed to exclude `R-Bus` replacement services from scheduled frequency
    # (README 5.4 item 5).
    platform_code: Mapped[str | None] = mapped_column(String(32))

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
