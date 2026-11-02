"""Unit tests for app.loaders.geo.transform -- pure, no database.

Builds a two-row GeoDataFrame with the real ASGS column names
(SA1_CODE26, STE_CODE26, ...) confirmed against the actual shapefile, so a
renamed or mistyped column in transform() fails here instead of three
layers downstream in a bulk upsert.
"""

import geopandas as gpd
from app.loaders.geo import METRIC_CRS, WGS84_CRS, transform
from shapely.geometry import Polygon

# A 1km x 1km square near Melbourne, in the shapefile's published CRS.
SQUARE = Polygon(
    [(144.95, -37.82), (144.96, -37.82), (144.96, -37.81), (144.95, -37.81)]
)


def _sample_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        [
            {
                "SA1_CODE26": "20101100101",
                "SA2_CODE26": "201011001",
                "SA2_NAME26": "Melbourne",
                "SA3_CODE26": "20101",
                "SA4_CODE26": "201",
                "GCC_CODE26": "2GMEL",
                "GCC_NAME26": "Greater Melbourne",
                "STE_CODE26": "2",
                "AREASQKM26": 1.0,
                "geometry": SQUARE,
            }
        ],
        crs=7844,
    )


def test_transform_maps_fields_and_converts_units():
    records = transform(_sample_gdf())

    assert len(records) == 1
    rec = records[0]
    assert rec["sa1_code"] == "20101100101"
    assert rec["edition"] == "2026"
    assert rec["sa1_code_2021"] is None  # filled later, by the correspondence loader
    assert rec["gcc_code"] == "2GMEL"
    assert rec["area_sqm"] == 1.0 * 1_000_000.0  # km^2 -> m^2


def test_transform_reprojects_to_both_target_crs():
    rec = transform(_sample_gdf())[0]

    assert rec["geom"].srid == METRIC_CRS
    assert rec["geom_4326"].srid == WGS84_CRS


def test_empty_geodataframe_returns_no_records():
    empty = _sample_gdf().iloc[0:0]

    assert transform(empty) == []
