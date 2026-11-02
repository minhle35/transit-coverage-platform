"""Unit tests for app.loaders.census.transform -- pure, no database.

Mirrors a real G01 row shape: one code column, one promoted population
column, and extra columns that must end up in `payload`, not as new
promoted fields.
"""

import pandas as pd  # noqa: I001

from app.loaders.census import transform


def test_transform_promotes_code_and_population():
    df = pd.DataFrame(
        [
            {"SA1_CODE_2021": 20101100101, "Tot_P_P": 435, "Age_0_4_yr_P": 12},
            {"SA1_CODE_2021": 20101100102, "Tot_P_P": 184, "Age_0_4_yr_P": 5},
        ]
    )

    records = transform(df)

    assert len(records) == 2
    first = records[0]
    assert first["sa1_code"] == "20101100101"  # str, not the source int64
    assert first["population"] == 435
    assert isinstance(first["population"], int)
    assert first["census_year"] == 2021


def test_unpromoted_columns_go_to_payload_not_top_level():
    df = pd.DataFrame(
        [{"SA1_CODE_2021": 20101100101, "Tot_P_P": 435, "Age_0_4_yr_P": 12}]
    )

    record = transform(df)[0]

    assert "Age_0_4_yr_P" not in record  # not a top-level column
    assert record["payload"]["Age_0_4_yr_P"] == 12
    assert "SA1_CODE_2021" not in record["payload"]  # promoted columns excluded
    assert "Tot_P_P" not in record["payload"]


def test_empty_dataframe_returns_no_records():
    df = pd.DataFrame(columns=["SA1_CODE_2021", "Tot_P_P"])

    assert transform(df) == []
