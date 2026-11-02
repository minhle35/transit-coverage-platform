"""Which composite key is unique over core.stop, and is dedup safe?

    cd backend && source .venv/bin/activate
    python scripts/duplicated_keys.py

The GTFS load dies with:
    psycopg.errors.CardinalityViolation:
    ON CONFLICT DO UPDATE command cannot affect row a second time

i.e. one INSERT proposed two rows with the same (feed_version_id, stop_id).
feed_version_id is a single hash for the whole load, so the key behaves as
stop_id alone.
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
GTFS = ROOT / "data" / "_published_public_transport_gtfs_schedule_gtfs"

# README 4.6 parameterises catchment and decay for four modes. The eight zone
# folders are operator branches, which collapse onto those four.
SCORING_MODES = {
    "1": "rail", "2": "rail", "10": "rail",
    "3": "tram",
    "4": "bus", "6": "bus", "11": "bus",
    "5": "coach",
}

frames = []
for zd in sorted(GTFS.iterdir()):
    p = zd / "google_transit" / "stops.txt"
    if p.exists():
        df = pd.read_csv(
            p,
            usecols=["stop_id", "stop_name", "stop_lat", "stop_lon"],
            dtype={"stop_id": str},
        )
        df["zone"] = zd.name
        frames.append(df)

c = pd.concat(frames, ignore_index=True)
c["mode"] = c.zone.map(SCORING_MODES)

print("rows                        :", len(c))
print("unique (stop_id)            :", len(c.drop_duplicates(["stop_id"])))
print("unique (stop_id, mode)      :", len(c.drop_duplicates(["stop_id", "mode"])))
print("unique (stop_id, zone)      :", len(c.drop_duplicates(["stop_id", "zone"])))

dup = c[c.duplicated("stop_id", keep=False)]
print("\nzone combinations that collide:")
for combo, n in (
    dup.groupby("stop_id").zone.apply(lambda s: "+".join(sorted(s, key=len)))
    .value_counts().items()
):
    modes = sorted({SCORING_MODES[z] for z in combo.split("+")})
    print(f"  {combo:<12}{n:>5}  {'/'.join(modes):<11}"
          f"{'same mode' if len(modes) == 1 else 'DISTINCT modes - must keep both'}")

# The decisive check. Co-located rows are one physical stop published in two
# operator feeds, so merging them is correct. Rows far apart would mean the id
# is reused for different places, and merging would relocate a stop --
# silently wrong distances for every SA1 nearby.
pts = gpd.GeoDataFrame(
    dup, geometry=gpd.points_from_xy(dup.stop_lon, dup.stop_lat), crs=4326
).to_crs(7899)
spread = pts.groupby("stop_id").geometry.apply(
    lambda g: max(
        (a.distance(b) for i, a in enumerate(g) for b in list(g)[i + 1:]), default=0.0
    )
)

print(f"\ncolliding ids                : {len(spread)}")
print(f"  identical coords (<1 m)    : {(spread < 1).sum():>5}  safe to merge")
print(f"  nearby (1-50 m)            : {((spread >= 1) & (spread <= 50)).sum():>5}  safe to merge")
print(f"  far apart (>50 m)          : {(spread > 50).sum():>5}  merging would corrupt")
print(f"  disagree on stop_name      : "
      f"{(dup.groupby('stop_id').stop_name.nunique() > 1).sum():>5}  needs a tiebreak")

"""
results:

rows                        : 32063
unique (stop_id)            : 31080      983 dupes
unique (stop_id, mode)      : 31438      625 dupes
unique (stop_id, zone)      : 32063        0 dupes

zone combinations that collide:
  1+2           347  rail        same mode
  5+6           223  bus/coach   DISTINCT modes - must keep both
  4+6           101  bus         same mode
  4+5            66  bus/coach   DISTINCT modes - must keep both
  1+2+10         61  rail        same mode
  3+4            40  bus/tram    DISTINCT modes - must keep both
  4+11           22  bus         same mode
  1+2+5          20  coach/rail  DISTINCT modes - must keep both
  4+5+6           9  bus/coach   DISTINCT modes - must keep both
  1+10            4  rail        same mode

colliding ids                : 893
  identical coords (<1 m)    :   893  safe to merge
  nearby (1-50 m)            :     0  safe to merge
  far apart (>50 m)          :     0  merging would corrupt
  disagree on stop_name      :    45  needs a tiebreak

stop_id is not unique -> cannot be PK alone.
(stop_id, zone) is unique, but zone is operator branch, not mode: keying on it
stores Flinders Street twice as rail and double-counts it in stops_within_400m.
(stop_id, mode) still collides (zones 1 and 2 are both rail), so it cannot be
the PK either -- but every collision is 0 m apart with matching names, so those
rows are one physical stop published in several feeds.

-> Keep PK (feed_version_id, stop_id). Dedup on (stop_id, mode) in transform():
   32063 -> 31438 rows. The 625 dropped rows are byte-identical in position.
   Rail frequency summed across both feeds belongs in stop_service_hourly,
   which is README 4.3's "platforms merged per mode".
   Dedup on stop_id alone would be wrong: it destroys the 358 stops that are
   genuinely two modes (coach+bus, tram+bus).
   45 ids need a deterministic stop_name tiebreak, else row order decides.
"""
