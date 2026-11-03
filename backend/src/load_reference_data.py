"""Orchestration script to run all data loaders
    SA1 boundaries, 2021 Census population into core.*.

    cd backend
    uv run alembic upgrade head          # tables must exist first
    uv run python src/load_reference_data.py

Each loader runs in its own transaction, so a failure in one does not
touch the other's already-committed rows.
"""

from pathlib import Path

from app.loaders import census, db, geo, gtfs

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data"

SHAPEFILE = DATA_DIR / "SA1_2021_AUST_SHP_GDA2020" / "SA1_2021_AUST_GDA2020.shp"
G01_CSV = (
    DATA_DIR
    / "2021_GCP_all_for_VIC_short-header"
    / "2021 Census GCP All Geographies for VIC"
    / "SA1"
    / "VIC"
    / "2021Census_G01_VIC_SA1.csv"
)

GTFS_ROOT = DATA_DIR / "_published_public_transport_gtfs_schedule_gtfs"


def main() -> None:
    print(f"Reading {SHAPEFILE.name} ...")
    areas = geo.transform(geo.extract(SHAPEFILE))
    with db.get_session() as session:
        n_areas = geo.load(areas, session)
    print(f"core.area_sa1: upserted {n_areas} rows")

    print(f"Reading {G01_CSV.name} ...")
    population = census.transform(census.extract(G01_CSV))
    with db.get_session() as session:
        n_pop = census.load(population, session)
    print(f"core.census_sa1: upserted {n_pop} rows")

    print(f"Reading GTFS from {GTFS_ROOT}")
    feed_version_id, stops_df = gtfs.extract_zipped_files(GTFS_ROOT)
    stops = gtfs.transform(feed_version_id, stops_df)

    with db.get_session() as session:
        n_stops = gtfs.load(stops, session)

    print(f"core.stop: upserted {n_stops} rows")
    print(f"Feed version: {feed_version_id}")


if __name__ == "__main__":
    main()
