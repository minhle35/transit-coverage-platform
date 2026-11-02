"""ASGS SA1 boundary loader: shapefile -> core.area_sa1.

Supports both 2021 and 2026 ASGS editions. The AreaSa1 table stores everything
in 2026 edition columns; if loading 2021 boundaries, edition='2021' is stored
and sa1_code_2021 is populated from the sa1_code field.
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
    """Read the national shapefile, keep Victoria only.

    Handles both 2021 (STE_CODE21) and 2026 (STE_CODE26) editions.
    """
    gdf = gpd.read_file(shapefile_path)
    # Detect edition from available columns
    if "STE_CODE26" in gdf.columns:
        ste_col = "STE_CODE26"
    elif "STE_CODE21" in gdf.columns:
        ste_col = "STE_CODE21"
    else:
        raise ValueError(f"Cannot find STE_CODE column. Available: {gdf.columns.tolist()}")
    return gdf[gdf[ste_col] == VIC_STE_CODE].copy()


def transform(gdf: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    """One dict per SA1, columns matching AreaSa1 exactly. Pure: no DB, no I/O.

    Handles both 2021 and 2026 editions, detected from column names.
    Reprojects once, here: `geom` is metric for distance, `geom_4326` is WGS84 for GeoJSON.
    """
    # Detect edition from available columns
    if "SA1_CODE26" in gdf.columns:
        edition = "2026"
        code_suffix = "26"
    elif "SA1_CODE21" in gdf.columns:
        edition = "2021"
        code_suffix = "21"
    else:
        raise ValueError(f"Cannot find SA1_CODE column. Available: {gdf.columns.tolist()}")

    metric_geoms = gdf.geometry.to_crs(METRIC_CRS)
    wgs84_geoms = gdf.geometry.to_crs(WGS84_CRS)

    records = []
    for row, geom_m, geom_w in zip(gdf.itertuples(index=False), metric_geoms, wgs84_geoms):
        sa1_code = getattr(row, f"SA1_CODE{code_suffix}")

        # Skip invalid/null geometries
        if geom_m is None or geom_w is None or geom_m.is_empty or geom_w.is_empty:
            continue

        records.append(
            {
                "sa1_code": str(sa1_code),
                "edition": edition,
                "sa1_code_2021": str(sa1_code) if edition == "2021" else None,
                "sa2_code": getattr(row, f"SA2_CODE{code_suffix}", None),
                "sa2_name": getattr(row, f"SA2_NAME{code_suffix}", None),
                "sa3_code": getattr(row, f"SA3_CODE{code_suffix}", None),
                "sa4_code": getattr(row, f"SA4_CODE{code_suffix}", None),
                "gcc_code": getattr(row, f"GCC_CODE{code_suffix}", None),
                "gcc_name": getattr(row, f"GCC_NAME{code_suffix}", None),
                "ste_code": getattr(row, f"STE_CODE{code_suffix}", None),
                "area_sqm": float(getattr(row, f"AREASQKM{code_suffix}", 0)) * 1_000_000.0,
                "geom": from_shape(geom_m, srid=METRIC_CRS),
                "geom_4326": from_shape(geom_w, srid=WGS84_CRS),
            }
        )
    return records


def load(records: list[dict[str, Any]], session: Session) -> int:
    """Upsert by sa1_code in batches. Re-running with the same input
    leaves the table in the same state -- that's the idempotency property.

    Batches inserts to stay under PostgreSQL's 65,535 parameter limit.
    """
    if not records:
        return 0

    batch_size = 5000  # ~60,000 params per batch (12 cols * 5000 rows)
    total = 0

    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        stmt = pg_insert(AreaSa1).values(batch)
        update_cols = {c: stmt.excluded[c] for c in batch[0] if c != "sa1_code"}
        stmt = stmt.on_conflict_do_update(
            index_elements=[AreaSa1.sa1_code], set_=update_cols
        )
        session.execute(stmt)
        session.commit()
        total += len(batch)

    return total
