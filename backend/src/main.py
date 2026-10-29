import pandas as pd  # noqa: I001
import geopandas as gpd
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
ROOT = CURRENT_FILE.parent.parent.parent
DATA_DIR = ROOT / "data"
GTFS_ZONE_1 = (
    DATA_DIR / "_published_public_transport_gtfs_schedule_gtfs/1/google_transit"
)
CENSUS_DATA = DATA_DIR / "2021_GCP_all_for_VIC_short-header"
SA1_DIR = DATA_DIR / "SA1_2026_AUST_SHP_GDA2020"

print("=" * 80)
print("EXPLORING DATA")
print("=" * 80)

stops_df = pd.read_csv(GTFS_ZONE_1 / "stops.txt")
print(f"Stops: {len(stops_df)} rows.")
print(stops_df.head())
print(f"\nData types: {stops_df.dtypes}")
print(f"\nColumns: {stops_df.columns.tolist()}")


# Read GTFS routes
routes_df = pd.read_csv(GTFS_ZONE_1 / "routes.txt")
print(f"\n\nRoutes: {len(routes_df)} rows")
print(routes_df.head())


# Read GTFS stop_times (large file!)
print("\nReading stop_times.txt (this is large, ~10k rows)...")
stop_times_df = pd.read_csv(GTFS_ZONE_1 / "stop_times.txt")
print(f"Stop times: {len(stop_times_df)} rows")
print(stop_times_df.head())

# Read GTFS calendar
calendar_df = pd.read_csv(GTFS_ZONE_1 / "calendar.txt")
print(f"\n\nCalendar: {len(calendar_df)} rows")
print(calendar_df.head())

print("\n" + "=" * 80)
print("EXPLORING CENSUS DATA")
print("=" * 80)

# Find census files
census_dir = CENSUS_DATA / "2021 Census GCP All Geographies for VIC"
csv_files = list(census_dir.glob("**/*.csv"))
print(f"\nFound {len(csv_files)} CSV files")
print("First few:", [f.name for f in csv_files[:5]])

# Read one census file (G01 table - population)
g01_files = list(census_dir.glob("**/G01*.csv"))
if g01_files:
    print("\nReading population data (G01 table)...")
    pop_df = pd.read_csv(g01_files[0])
    print(f"Rows: {len(pop_df)}")
    print(pop_df.head())
    print(f"\nColumns: {pop_df.columns.tolist()}")

print("\n" + "=" * 80)
print("EXPLORING SA1 BOUNDARIES (Shapefile)")
print("=" * 80)

# Read shapefile
shp_file = SA1_DIR / "SA1_2026_AUST_GDA2020.shp"
gdf = gpd.read_file(shp_file)
print(f"\nSA1 shapes: {len(gdf)} rows")
print(f"CRS: {gdf.crs}")
print(gdf.head())
print(f"\nColumns: {gdf.columns.tolist()}")
print(f"\nGeometry type: {gdf.geometry.type.unique()}")

# Filter to Victoria only
vic_code = gdf[gdf["SA1_CODE26"].astype(str).str.startswith("2")].copy()
print(f"\nVictoria only: {len(vic_code)} SA1s")
