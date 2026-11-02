"""Unit tests for app.loaders.gtfs.transform -- pure, no database."""

import pandas as pd
from app.loaders.gtfs import transform

SAMPLE_FEED_VERSION = "a3f42c1e8b9d7e6f5c4b3a2d1e0f9a8b"


def _sample_stops_df() -> pd.DataFrame:
    """Sample GTFS stops data with expected columns."""
    return pd.DataFrame(
        [
            {
                "stop_id": "1001",
                "stop_code": 1001.0,
                "stop_name": "Collins St / Spring St",
                "stop_lat": -37.8140,
                "stop_lon": 144.9675,
                "location_type": 0,  # platform
                "parent_station": None,
                "wheelchair_boarding": 1.0,
                "zone": "3",  # tram zone
                "platform_code": "1",
                "level_id": None,
            },
            {
                "stop_id": "2001",
                "stop_code": 2001.0,
                "stop_name": "Southern Cross",
                "stop_lat": -37.8182,
                "stop_lon": 144.9534,
                "location_type": 1,  # station
                "parent_station": None,
                "wheelchair_boarding": 1.0,
                "zone": "2",  # metro train
                "platform_code": None,
                "level_id": "1",
            },
        ]
    )


def test_transform_creates_point_geometries():
    """Verify dual-CRS Point geometries are created."""
    records = transform(SAMPLE_FEED_VERSION, _sample_stops_df())

    assert len(records) == 2
    for record in records:
        assert "geom" in record  # metric 7899
        assert "geom_4326" in record  # WGS84 4326
        assert record["geom"] is not None
        assert record["geom_4326"] is not None


def test_transform_populates_feed_version_id():
    """Verify feed_version_id is set on all records."""
    records = transform(SAMPLE_FEED_VERSION, _sample_stops_df())

    assert all(r["feed_version_id"] == SAMPLE_FEED_VERSION for r in records)


def test_transform_materializes_location_type_flags():
    """Verify is_platform and is_station are set correctly."""
    records = transform(SAMPLE_FEED_VERSION, _sample_stops_df())

    # First row: location_type 0 = platform
    assert records[0]["is_platform"] is True
    assert records[0]["is_station"] is False

    # Second row: location_type 1 = station
    assert records[1]["is_platform"] is False
    assert records[1]["is_station"] is True


def test_transform_handles_null_wheelchair_boarding():
    """Null wheelchair_boarding defaults to 0."""
    df = _sample_stops_df()
    df.loc[0, "wheelchair_boarding"] = None

    records = transform(SAMPLE_FEED_VERSION, df)
    assert records[0]["wheelchair_boarding"] == 0


def test_transform_handles_valid_records():
    """Transform processes all valid records."""
    df = _sample_stops_df()

    records = transform(SAMPLE_FEED_VERSION, df)
    # Both records have valid coordinates
    assert len(records) == 2
    assert records[0]["stop_id"] == "1001"
    assert records[1]["stop_id"] == "2001"


def test_transform_preserves_zone_field():
    """Zone field is preserved from source data."""
    records = transform(SAMPLE_FEED_VERSION, _sample_stops_df())

    assert records[0]["zone"] == "3"
    assert records[1]["zone"] == "2"


def test_transform_converts_stop_id_to_string():
    """stop_id is always a string, even if numeric in source."""
    records = transform(SAMPLE_FEED_VERSION, _sample_stops_df())

    assert isinstance(records[0]["stop_id"], str)
    assert records[0]["stop_id"] == "1001"
