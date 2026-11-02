"""Unit tests for geo.py edition detection (2021 vs 2026)."""

import geopandas as gpd
from app.loaders.geo import transform
from shapely.geometry import Polygon

SQUARE = Polygon(
    [(144.95, -37.82), (144.96, -37.82), (144.96, -37.81), (144.95, -37.81)]
)


def _gdf_2021() -> gpd.GeoDataFrame:
    """Sample 2021 ASGS Edition 3 GeoDataFrame."""
    return gpd.GeoDataFrame(
        [
            {
                "SA1_CODE21": "20101100101",
                "SA2_CODE21": "201011001",
                "SA2_NAME21": "Melbourne",
                "SA3_CODE21": "20101",
                "SA4_CODE21": "201",
                "GCC_CODE21": "2GMEL",
                "GCC_NAME21": "Greater Melbourne",
                "STE_CODE21": "2",
                "AREASQKM21": 1.0,
                "geometry": SQUARE,
            }
        ],
        crs=7844,
    )


def _gdf_2026() -> gpd.GeoDataFrame:
    """Sample 2026 ASGS Edition 4 GeoDataFrame."""
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


def test_transform_detects_2021_edition():
    """Transform detects 2021 edition by column names."""
    records = transform(_gdf_2021())

    assert len(records) == 1
    assert records[0]["edition"] == "2021"
    assert records[0]["sa1_code"] == "20101100101"
    assert records[0]["sa1_code_2021"] == "20101100101"  # Filled for 2021 edition


def test_transform_detects_2026_edition():
    """Transform detects 2026 edition by column names."""
    records = transform(_gdf_2026())

    assert len(records) == 1
    assert records[0]["edition"] == "2026"
    assert records[0]["sa1_code"] == "20101100101"
    assert records[0]["sa1_code_2021"] is None  # Not filled for 2026 edition


def test_transform_2021_fills_sa1_code_2021():
    """For 2021 edition, sa1_code_2021 is populated from sa1_code."""
    records = transform(_gdf_2021())

    assert records[0]["sa1_code_2021"] is not None
    assert records[0]["sa1_code_2021"] == records[0]["sa1_code"]


def test_transform_2026_leaves_sa1_code_2021_null():
    """For 2026 edition, sa1_code_2021 stays NULL."""
    records = transform(_gdf_2026())

    assert records[0]["sa1_code_2021"] is None


def test_transform_both_editions_reproject_geometry():
    """Both editions produce dual-CRS geometries."""
    for gdf in [_gdf_2021(), _gdf_2026()]:
        records = transform(gdf)
        assert records[0]["geom"] is not None  # Metric 7899
        assert records[0]["geom_4326"] is not None  # WGS84 4326
