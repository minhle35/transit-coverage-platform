"""GTFS stops loader: stops.txt from all zones -> core.stop.

Loads from zone folders (1-11), each containing google_transit/stops.txt.
Uses the latest ZIP in each zone to compute feed_version_id as SHA-256.

A zone folder is an *operational branch*, not a transport mode -- Transport
Victoria publishes one ZIP per administrative unit. README 5.2 has the full
account; the two mappings below are deliberately separate because folder
numbers and GTFS route_type numbers share digits that mean different things
(folder 3 is tram, route_type 3 is bus; folder 11 is SkyBus, route_type 11 is
trolleybus).
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

# Folder -> operational branch. Provenance only: recorded in `stop.zone` so a
# mapping error is re-derivable without re-reading 2 GB of GTFS.
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

# Folder -> scoring mode. This is what the formula consumes: README 4.6
# parameterises R_m and w_m for exactly these three. Modes are grouped by
# right-of-way, not vehicle technology, because that is what drives both
# catchment size and reliability -- so Melbourne's street-running trams sit
# apart from grade-separated rail, and regional coach collapses into bus.
#
# Corroborated by routes.txt route_type for all eight folders (README 5.2):
#   rail <- 2, 102, 400    tram <- 0    bus <- 3, 204, 701
SCORING_MODES = {
    "1": "rail",  # Regional Train      route_type 2
    "2": "rail",  # Metropolitan Train  route_type 400
    "10": "rail",  # Interstate          route_type 102
    "3": "tram",  # Metropolitan Tram   route_type 0
    "4": "bus",  # Myki Bus            route_type 3, 701
    "6": "bus",  # Regional Bus        route_type 701
    "11": "bus",  # SkyBus              route_type 3
    "5": "bus",  # Regional Coach      route_type 204
}

def extract(gtfs_root: Path) -> tuple[str, pd.DataFrame]:
    """Read stops.txt from every GTFS zone, compute the feed version hash.

    Returns (feed_version_id, combined_stops_df). feed_version_id is the
    SHA-256 of the most recent google_transit.zip across all zones.

    Loads the whole feed. Study-area scope is applied where results are
    computed, not here -- see app/study_area.py for why.
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
    print(f"Total stops across all zones: {len(combined)}")

    if not latest_zip_path:
        raise ValueError("No google_transit.zip found to compute feed_version_id")

    feed_version_id = hashlib.sha256(latest_zip_path.read_bytes()).hexdigest()
    print(f"Feed version SHA-256: {feed_version_id}")

    print()

    return feed_version_id, combined


def _dedupe_stop_mode(stops_df: pd.DataFrame) -> pd.DataFrame:
    """Collapse rows that are one physical stop published in several branches.

    Each operational branch ships its own feed, so a stop served by two
    branches appears once per branch and `stop_id` is not unique across the
    snapshot (32,063 rows, 31,080 distinct ids). Loading that under a
    (feed_version_id, stop_id) key fails: PostgreSQL rejects an ON CONFLICT DO
    UPDATE whose statement proposes the same key twice.

    Collapsing on (stop_id, mode) is safe because every collision measured in
    the snapshot sits at *identical* coordinates with matching names -- one
    platform, published repeatedly (Flinders Street 11212 is at the same point
    in both the Regional and Metropolitan Train feeds). See
    scripts/duplicated_keys.py for the measurement.

    Collapsing on `stop_id` alone would be wrong: 358 stops are genuinely
    served by two modes (coach and bus, or tram and bus) and must survive as
    separate stop-mode pairs, which is the unit README 4.2 sums over.

    Frequency summed across branches belongs in core.stop_service_hourly, not
    in duplicated stop rows (README 4.3). The surviving row keeps the
    lowest-numbered contributing branch in `zone`, so that column names one
    real source rather than an invented composite.
    """
    df = stops_df.copy()
    df["stop_id"] = df["stop_id"].astype(str)
    df["zone"] = df["zone"].astype(str)
    df["mode"] = df["zone"].map(SCORING_MODES)

    unmapped = sorted(df.loc[df["mode"].isna(), "zone"].unique())
    if unmapped:
        raise ValueError(
            f"Zone folders absent from SCORING_MODES: {unmapped}. "
            "Add them, or the stops load with a null mode and score as unreachable."
        )

    before = len(df)
    df = (
        df.assign(_zone_order=df["zone"].astype(int))
        .sort_values(["stop_id", "mode", "_zone_order"])
        .drop_duplicates(["stop_id", "mode"], keep="first")
        .drop(columns="_zone_order")
    )
    if before != len(df):
        print(f"Merged {before - len(df)} stop-mode duplicates: {before} -> {len(df)}")
    return df


def transform(feed_version_id: str, stops_df: pd.DataFrame) -> list[dict[str, Any]]:
    """One dict per stop-mode pair, keyed to match the Stop model.

    Pure: no database, no I/O.

    Resolves `mode` from the zone folder via SCORING_MODES and collapses
    stop-mode duplicates (see _dedupe_stop_mode), then builds the dual-CRS
    geometry pair: metric 7899 for distance, WGS84 4326 for GeoJSON.

    `stop_lat`, `stop_lon` and `zone` are read but not returned -- the first two
    become geometry, the third resolves mode. Position is stored once, as
    geometry (README 3.2).
    """
    stops_df = _dedupe_stop_mode(stops_df)

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
                "mode": row.mode,
                "stop_name": row.stop_name if pd.notna(row.stop_name) else None,
                "location_type": location_type,
                "parent_station": (
                    str(row.parent_station) if pd.notna(row.parent_station) else None
                ),
                # GTFS enum; a blank in the feed means "no information" (0).
                "wheelchair_boarding": (
                    int(row.wheelchair_boarding)
                    if pd.notna(row.wheelchair_boarding)
                    else 0
                ),
                "platform_code": (
                    str(row.platform_code) if pd.notna(row.platform_code) else None
                ),
                # stop_lat/stop_lon and zone are source fields only: the former
                # become `geom`/`geom_4326` below, the latter resolves `mode` in
                # _dedupe_stop_mode. Neither is stored -- see README 3.2 on
                # geometry being the single representation of position.
                "geom": from_shape(geom_m, srid=METRIC_CRS),
                "geom_4326": from_shape(geom_w, srid=WGS84_CRS),
            }
        )
    return records


def load(records: list[dict[str, Any]], session: Session) -> int:
    """Upsert by (feed_version_id, stop_id, mode) in batches.

    The conflict target must be the full primary key: `stop_id` alone is not
    unique, and 60 stop_ids legitimately serve two modes.

    Batched to stay under PostgreSQL's 65,535 bind-parameter ceiling -- ten
    columns per row, so 2,000 rows is ~20,000 parameters.
    """
    if not records:
        return 0

    batch_size = 2000
    total = 0

    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        stmt = pg_insert(Stop).values(batch)
        update_cols = {
            c: stmt.excluded[c]
            for c in batch[0]
            if c not in ("feed_version_id", "stop_id", "mode")
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=[Stop.feed_version_id, Stop.stop_id, Stop.mode],
            set_=update_cols,
        )
        session.execute(stmt)
        session.commit()
        total += len(batch)

    return total
