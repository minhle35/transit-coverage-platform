"""2021 Census G01 loader: CSV -> core.census_sa1.

`sa1_code` here is a **2021** SA1 code -- a different code space from
`core.area_sa1.sa1_code`, which is 2026. Only `Tot_P_P` is promoted to a
column, per the model's own docstring: the other ~105 age/sex columns in
G01 go into `payload` (JSONB) so they're queryable later without a
migration, instead of being imported as 105 mostly-unused columns. That
decision follows directly from the scoring formula, which only ever needs
total population -- see the "does this field feed the formula" test from
the data-modelling discussion.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.geo import CensusSa1

CODE_COL = "SA1_CODE_2021"
POPULATION_COL = "Tot_P_P"
CENSUS_YEAR = 2021


def extract(g01_csv_path: Path) -> pd.DataFrame:
    return pd.read_csv(g01_csv_path)


def transform(df: pd.DataFrame) -> list[dict[str, Any]]:
    """One dict per SA1. `to_dict(orient="records")` converts numpy scalars
    to native Python types, which JSONB needs for `payload`."""
    other_cols = [c for c in df.columns if c not in (CODE_COL, POPULATION_COL)]

    records = []
    for row in df.to_dict(orient="records"):
        records.append(
            {
                "sa1_code": str(row[CODE_COL]),
                "census_year": CENSUS_YEAR,
                "population": int(row[POPULATION_COL]),
                "payload": {c: row[c] for c in other_cols},
            }
        )
    return records


def load(records: list[dict[str, Any]], session: Session) -> int:
    if not records:
        return 0
    stmt = pg_insert(CensusSa1).values(records)
    update_cols = {c: stmt.excluded[c] for c in records[0] if c != "sa1_code"}
    stmt = stmt.on_conflict_do_update(index_elements=[CensusSa1.sa1_code], set_=update_cols)
    session.execute(stmt)
    return len(records)
