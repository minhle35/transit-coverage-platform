"""Proximity queries: thin wrapper around PostGIS spatial functions.

This module is the ONLY place spatial SQL functions are called from. It isolates
SQL from application logic and provides a clean Python interface for:
- Finding nearest stops (distance metric)
- Finding all stops in catchment (coverage metric)
- Finding max departures in catchment (frequency metric)

Design principle (README 3.2): PostGIS is the system of record for all spatial
operations. This wrapper is just row unpacking and type conversion.
"""

from __future__ import annotations

from typing import Sequence

from geoalchemy2 import Geometry
from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

__all__ = [
    "nearest_stop_by_mode",
    "stops_within_radius",
    "max_departures_in_catchment",
]


def nearest_stop_by_mode(
    session: Session,
    origin_geom: Geometry,
    mode: str,
    feed_version: str,
) -> Row | None:
    """Find the single closest stop of a given mode to an origin point.

    Args:
        session: SQLAlchemy session
        origin_geom: Point geometry (EPSG:7899, metres)
        mode: One of 'rail', 'tram', 'bus', 'coach'
        feed_version: Feed version ID from ops.feed_version.feed_version_id

    Returns:
        Row with (stop_id, distance_m, stop_name, geom, geom_4326), or None.
        None indicates no matching stop, invalid input, or feed version not found.

    Example:
        >>> result = nearest_stop_by_mode(session, origin_point, 'tram', feed_id)
        >>> if result:
        ...     print(f"{result.stop_name}: {result.distance_m}m away")
    """
    result = session.execute(
        text("""
            SELECT stop_id, distance_m, stop_name, geom, geom_4326
            FROM core.nearest_stop_by_mode(:origin, :mode, :feed_version)
        """),
        {"origin": origin_geom, "mode": mode, "feed_version": feed_version},
    ).fetchone()
    return result


def stops_within_radius(
    session: Session,
    origin_geom: Geometry,
    radius_m: float,
    mode: str,
    feed_version: str,
) -> Sequence[Row]:
    """Find all stops of a given mode within a radius of an origin point.

    Args:
        session: SQLAlchemy session
        origin_geom: Point geometry (EPSG:7899, metres)
        radius_m: Search radius in metres (must be > 0)
        mode: One of 'rail', 'tram', 'bus', 'coach'
        feed_version: Feed version ID from ops.feed_version.feed_version_id

    Returns:
        Sequence of Row objects with (stop_id, distance_m, stop_name, geom, geom_4326),
        ordered by ascending distance. Empty sequence if no stops match or input invalid.

    Example:
        >>> stops = stops_within_radius(session, origin_point, 400, 'tram', feed_id)
        >>> for stop in stops:
        ...     print(f"{stop.stop_name}: {stop.distance_m}m away")
    """
    results = session.execute(
        text("""
            SELECT stop_id, distance_m, stop_name, geom, geom_4326
            FROM core.stops_within_radius(:origin, :radius, :mode, :feed_version)
        """),
        {
            "origin": origin_geom,
            "radius": radius_m,
            "mode": mode,
            "feed_version": feed_version,
        },
    ).fetchall()
    return results


def max_departures_in_catchment(
    session: Session,
    origin_geom: Geometry,
    radius_m: float,
    mode: str,
    feed_version: str,
    day_type: str,
    hour: int,
) -> int | None:
    """Find the maximum hourly departures across all stops within a catchment.

    Args:
        session: SQLAlchemy session
        origin_geom: Point geometry (EPSG:7899, metres)
        radius_m: Catchment radius in metres (typically 400 or 800; must be > 0)
        mode: One of 'rail', 'tram', 'bus', 'coach'
        feed_version: Feed version ID from ops.feed_version.feed_version_id
        day_type: One of 'weekday', 'saturday', 'sunday'
        hour: Hour of day (0-23, typically 8 for morning peak)

    Returns:
        Integer max departures/hour within the catchment, or None if:
        - No stops match the criteria
        - No service data exists for the time window
        - Input is invalid

    Example:
        >>> freq = max_departures_in_catchment(
        ...     session, origin_point, 400, 'tram', feed_id, 'weekday', 8
        ... )
        >>> if freq:
        ...     print(f"Best tram frequency: {freq} departures/hour")
    """
    result = session.execute(
        text("""
            SELECT core.max_departures_in_catchment(
                :origin, :radius, :mode, :feed_version, :day_type, :hour
            ) AS max_deps
        """),
        {
            "origin": origin_geom,
            "radius": radius_m,
            "mode": mode,
            "feed_version": feed_version,
            "day_type": day_type,
            "hour": hour,
        },
    ).scalar()
    return result
