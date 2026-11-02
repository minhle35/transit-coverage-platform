"""GTFS stops loader: stops.txt from all zones -> core.stop.

Loads from zone folders (1-11), each containing google_transit/stops.txt.
Treats each zone as a transport mode (zone 1 = Regional Train, zone 2 = Metro Train, etc).
Uses the latest ZIP in each zone to compute feed_version_id as SHA-256.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from geoalchemy2.shape import from_shape
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.gtfs import Stop

METRIC_CRS = 7899
WGS84_CRS = 4326

ZONE_MODES = {
    "1": "Regional Train",
    "2": "Metropolitan Train",
    "3": "Metropolitan Tram",
    "4": "Myki Bus",
    "5": "Regional Coach",
    "6": "Regional Bus",
    "10": "Interstate",
    "11": "SkyBus",
}


def extract(gtfs_root: Path) -> tuple[str, pd.DataFrame]:
    """Read stops.txt from all GTFS zones, compute feed version hash.

    Returns (feed_version_id, combined_stops_df).
    feed_version_id is the SHA-256 of the most recent google_transit.zip across all zones.
    """
    all_stops = []
    latest_zip_path = None
    latest_zip_mtime = 0

    for zone_dir in sorted(gtfs_root.iterdir()):
        if not zone_dir.is_dir():
            continue

        zone_zip = zone_dir / "google_transit.zip"
        if zone_zip.exists():
            mtime = zone_zip.stat().st_mtime
            if mtime > latest_zip_mtime:
                latest_zip_path = zone_zip
                latest_zip_mtime = mtime

        stops_path = zone_dir / "google_transit" / "stops.txt"
        if not stops_path.exists():
            continue

        try:
            zone_stops = pd.read_csv(stops_path)
            zone_stops["zone"] = zone_dir.name
            all_stops.append(zone_stops)
            print(f"Zone {zone_dir.name}: {len(zone_stops)} stops")
        except (pd.errors.ParserError, OSError) as e:
            print(f"Error reading {zone_dir.name}: {e}")

    if not all_stops:
        raise ValueError("No stops found in any zone")

    combined = pd.concat(all_stops, ignore_index=True)
    print(f"Total stops across all zones: {len(combined)}\n")

    if not latest_zip_path:
        raise ValueError("No google_transit.zip found to compute feed_version_id")

    feed_version_id = hashlib.sha256(latest_zip_path.read_bytes()).hexdigest()
    print(f"Feed version SHA-256: {feed_version_id}\n")

    return feed_version_id, combined


def transform(feed_version_id: str, stops_df: pd.DataFrame) -> list[dict[str, Any]]:
    """One dict per stop, columns matching Stop model. Pure: no DB, no I/O.

    Creates dual-CRS Point geometries (metric 7899 + WGS84 4326).
    Maps zone to mode name.
    Materializes is_platform and is_station flags.
    """
    gdf = gpd.GeoDataFrame(
        stops_df,
        geometry=gpd.points_from_xy(stops_df["stop_lon"], stops_df["stop_lat"]),
        crs=WGS84_CRS,
    )

    metric_geoms = gdf.geometry.to_crs(METRIC_CRS)
    wgs84_geoms = gdf.geometry

    records = []
    for row, geom_m, geom_w in zip(
        stops_df.itertuples(index=False), metric_geoms, wgs84_geoms
    ):
        # Skip invalid/null geometries
        if geom_m is None or geom_w is None or geom_m.is_empty or geom_w.is_empty:
            continue

        location_type = int(row.location_type) if pd.notna(row.location_type) else 0
        records.append(
            {
                "feed_version_id": feed_version_id,
                "stop_id": str(row.stop_id),
                "stop_code": row.stop_code if pd.notna(row.stop_code) else None,
                "stop_name": row.stop_name if pd.notna(row.stop_name) else None,
                "stop_lat": float(row.stop_lat) if pd.notna(row.stop_lat) else None,
                "stop_lon": float(row.stop_lon) if pd.notna(row.stop_lon) else None,
                "location_type": location_type,
                "parent_station": (
                    str(row.parent_station) if pd.notna(row.parent_station) else None
                ),
                "wheelchair_boarding": (
                    row.wheelchair_boarding if pd.notna(row.wheelchair_boarding) else 0
                ),
                "zone": str(row.zone),
                "platform_code": (
                    str(row.platform_code) if pd.notna(row.platform_code) else None
                ),
                "level_id": str(row.level_id) if pd.notna(row.level_id) else None,
                "is_platform": location_type == 0,
                "is_station": location_type == 1,
                "geom": from_shape(geom_m, srid=METRIC_CRS),
                "geom_4326": from_shape(geom_w, srid=WGS84_CRS),
            }
        )
    return records


def load(records: list[dict[str, Any]], session: Session) -> int:
    """Upsert by (feed_version_id, stop_id) in batches (stay under 65,535 params)."""
    if not records:
        return 0

    batch_size = 5000
    total = 0

    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        stmt = pg_insert(Stop).values(batch)
        update_cols = {
            c: stmt.excluded[c]
            for c in batch[0]
            if c not in ("feed_version_id", "stop_id")
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=[Stop.feed_version_id, Stop.stop_id],
            set_=update_cols,
        )
        session.execute(stmt)
        total += len(batch)

    return total
