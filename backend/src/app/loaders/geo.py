"""ASGS SA1 boundary loader: shapefile -> core.area_sa1.

Writes the 2026 edition only. `sa1_code_2021` stays NULL here -- filling it
is a separate loader that needs the ABS 2021->2026 correspondence file,
which is not yet downloaded (see README section 5.4/5.5). Loading the two
independently, and leaving the join as a visible gap, is deliberate: a
silently-empty `sa1_code_2021` is a correctness problem; a silently-guessed
one would be worse.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
from geoalchemy2.shape import from_shape
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.geo import AreaSa1

SOURCE_CRS = 7844  # GDA2020 geographic, as published -- geopandas reads this from the .prj
METRIC_CRS = 7899  # VicGrid: every distance/area calculation uses this
WGS84_CRS = 4326  # API/GeoJSON edge only

VIC_STE_CODE = "2"  # ABS state code for Victoria (STE_CODE26), not a string prefix on SA1_CODE26


def extract(shapefile_path: Path) -> gpd.GeoDataFrame:
    """Read the national shapefile, keep Victoria only."""
    gdf = gpd.read_file(shapefile_path)
    return gdf[gdf["STE_CODE26"] == VIC_STE_CODE].copy()


def transform(gdf: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    """One dict per SA1, columns matching AreaSa1 exactly. Pure: no DB, no I/O.

    Reprojects once, here, rather than per-query later: `geom` is the metric
    copy every distance calculation will use, `geom_4326` is the WGS84 copy
    the API will serve as GeoJSON.
    """
    metric_geoms = gdf.geometry.to_crs(METRIC_CRS)
    wgs84_geoms = gdf.geometry.to_crs(WGS84_CRS)

    records = []
    for row, geom_m, geom_w in zip(gdf.itertuples(index=False), metric_geoms, wgs84_geoms):
        records.append(
            {
                "sa1_code": str(row.SA1_CODE26),
                "edition": "2026",
                "sa1_code_2021": None,
                "sa2_code": row.SA2_CODE26,
                "sa2_name": row.SA2_NAME26,
                "sa3_code": row.SA3_CODE26,
                "sa4_code": row.SA4_CODE26,
                "gcc_code": row.GCC_CODE26,
                "gcc_name": row.GCC_NAME26,
                "ste_code": row.STE_CODE26,
                "area_sqm": float(row.AREASQKM26) * 1_000_000.0,
                "geom": from_shape(geom_m, srid=METRIC_CRS),
                "geom_4326": from_shape(geom_w, srid=WGS84_CRS),
            }
        )
    return records


def load(records: list[dict[str, Any]], session: Session) -> int:
    """Upsert by sa1_code in one statement. Re-running with the same input
    leaves the table in the same state -- that's the idempotency property."""
    if not records:
        return 0
    stmt = pg_insert(AreaSa1).values(records)
    update_cols = {c: stmt.excluded[c] for c in records[0] if c != "sa1_code"}
    stmt = stmt.on_conflict_do_update(index_elements=[AreaSa1.sa1_code], set_=update_cols)
    session.execute(stmt)
    return len(records)
