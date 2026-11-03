# Data Loaders: Architecture & Implementation

This document describes how each loader in `backend/src/app/loaders/` works, the data flow, and validation gates.

## Design Principles

1. **Extract-Transform-Load (ETL):** Each loader has three phases:
   - **Extract:** Read from files or source data
   - **Transform:** Pure Python (no database I/O) to prepare records
   - **Load:** Upsert to database, handling conflicts

2. **Idempotency:** Loaders use upsert (`INSERT ... ON CONFLICT DO UPDATE`) so re-running with the same data never creates duplicates.

3. **Single Transaction:** Each loader completes or fails wholly; the orchestration script (`load_reference_data.py`) runs each loader in its own transaction so one failure doesn't roll back the others.

4. **Study Area Scope:** Loaders read all data (Victoria-wide) without filtering; study-area filtering (to Greater Melbourne GCCSA 2GMEL) is applied when results are computed (see `app/study_area.py`), not during load. This allows re-scoping analysis without reloading data.

## Loaders

### `geo.py` — SA1 Boundaries

**Source:** ASGS Edition 3 SA1 shapefile (2021 census geography)  
**Target:** `core.area_sa1`  
**Transform:** Converts WGS84 → EPSG:7899 (metric) for distance calculations

**Key points:**
- One row per SA1 code (15,478 unique SA1s in Victoria)
- Dual CRS: `geom` (7899 metric), `geom_4326` (WGS84 for GeoJSON)
- `gcc_code` field used to filter to study area at compute time

**Validation:** Verify geometry is valid and falls within Victoria bounding box

```python
geo.extract(shapefile_path)      # Read, compute bounds
geo.transform(raw_df)            # Convert CRS, validate
geo.load(records, session)       # Upsert to core.area_sa1
```

---

### `census.py` — Population by SA1

**Source:** 2021 ABS Census, SA1-level (G01 series)  
**Target:** `core.census_sa1`  
**Key column:** `population` (age + sex group counts summed)

**Key points:**
- One row per SA1 code
- Excludes pseudo-SA1s used for confidentiality (4 rows with codes `29797979991–999`, `29999949999`)
- Total Victoria population (excluding pseudo-SA1s): 6,494,200 (checked before equity calculation)

**Validation:** Ensure population > 0 for real SA1s; zero population acceptable for pseudo-SA1s

```python
census.extract(g01_csv_path)     # Read CSV
census.transform(raw_df)         # Parse, dedup
census.load(records, session)    # Upsert to core.census_sa1
```

---

### `gtfs.py` — GTFS Stops

**Source:** Transport Victoria GTFS feeds (zones 1–11, excluding zone 8)  
**Target:** `core.stop`  
**Transform:** Deduplicates stops published in multiple branches; resolves mode from folder

**Key points:**
- **Folder structure:** Each operational branch (zone 1–11) is a folder; `google_transit.zip` contains `stops.txt`
- **Mode mapping:** Folder → SCORING_MODES (rail/tram/bus) not ZONE_MODES (operational names)
- **Deduplication:**
  - Some stops (e.g., Flinders Street) appear in multiple feeds (Regional + Metropolitan Train)
  - Collapsed on `(stop_id, mode)` because 358 stops genuinely serve two modes (tram + bus, coach + bus)
  - When collapsing, keeps lowest-numbered zone to preserve single source attribution
- **Dual CRS:** `geom` (7899), `geom_4326` (WGS84)
- **Feed version:** SHA-256 of latest `google_transit.zip` across all zones (makes load idempotent)

**Validation:**
- All coordinates fall within Victoria bounding box
- Geometry is valid (no empty/null geometries)
- Mode is not null (all zones mapped)

**Test:** 31,438 unique stop-mode pairs (32,063 rows deduplicated), 358 dual-mode stops, 45 name collisions expected

```python
feed_id, stops_df = gtfs.extract(gtfs_root)      # Read all zones, compute SHA-256
stops = gtfs.transform(feed_id, stops_df)        # Dedup, map modes, convert CRS
n = gtfs.load(stops, session)                    # Upsert to core.stop
```

---

### `feed_version.py` — Feed Version Metadata

**Source:** Computed from loader run (feed_version_id SHA-256, row counts)  
**Targets:** `ops.feed_version` + singleton `ops.active_version`  
**Idempotency:** keyed by SHA-256, so same feed re-loaded updates metadata, never duplicates

**Key points:**
- **ops.feed_version:** Records every archived GTFS download with metadata (URL, SHA-256, status, row counts)
- **ops.active_version:** Single row (id=1) that points to the currently-serving feed_version_id
- **Atomic promotion:** Promotion (staging → core, set active_version) is one transaction; rollback keeps previous version live
- **History:** All versions retained in ops.feed_version for audit trail

**Flow:**
1. Loader runs (geo, census, gtfs) — records into staging or core with new feed_version_id
2. `feed_version.load_feed_version()` upserts metadata to ops.feed_version
3. Sets ops.active_version.feed_version_id to new version (or leaves it if set_active=False)
4. Airflow gates can then decide whether to promote or roll back

**Test:** Duplicate feeds upsert; distinct feeds both retained; active_version updates

```python
metadata = feed_version.extract_metadata(sha, url, row_counts)
feed_version.load_feed_version(metadata, session, set_active=True)
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────┐
│ load_reference_data.py (orchestration)                  │
└──────┬───────────────┬───────────────┬──────────────────┘
       │               │               │
       v               v               v
   ┌───────────┐  ┌─────────┐  ┌─────────┐
   │ geo.py    │  │ census  │  │ gtfs.py │
   │ SA1 boundaries
   │ → core.area_sa1
   │           │  │ .py     │  │ Stops   │
   │           │  │ Pop     │  │ → core  │
   │           │  │ → core  │  │ .stop   │
   └─────┬─────┘  │ .census │  └────┬────┘
         │        │ _sa1    │       │
         │        └────┬────┘       │
         │             │           │
         └──────┬──────┴─────┬──────┘
                │            │
                v            v
         ┌─────────────────────────┐
         │ feed_version.py         │
         │ ops.feed_version record │
         │ ops.active_version set  │
         └────────┬────────────────┘
                  │
                  v
         ┌─────────────────────┐
         │ Staging complete    │
         │ Ready for promotion │
         │ (or rollback)       │
         └─────────────────────┘
```

---

## Quality Gates

These are enforced during load and recorded to `ops.dq_result` by the Airflow DAG (Phase 4):

| Gate | Threshold | Why |
|------|-----------|-----|
| **Census join rate** | ≥99.97% (15,478 SA1s) | Ensures stop-population correspondence is near-complete |
| **Service horizon** | ≥14 future days | Feed must have sufficient future service days to represent typical patterns |
| **Service carry-over** | ≥95% of prior version (±2% tolerance) | Detects missing zones or broken feeds |
| **Geographic bounds** | All coordinates within Victoria bbox | Prevents loading out-of-scope or malformed coordinates |
| **Row count drift** | ±10% of prior version | Detects subtle schema or truncation errors |

---

## Running Loaders Manually

```bash
cd backend
uv run alembic upgrade head          # Ensure schema exists
uv run python src/load_reference_data.py
```

Output:
```
Reading SA1_2021_AUST_SHP_GDA2020.shp ...
core.area_sa1: upserted 15478 rows
Reading 2021Census_G01_VIC_SA1.csv ...
core.census_sa1: upserted 15478 rows
Reading GTFS from data/_published_public_transport_gtfs_schedule_gtfs
Zone 1: 232 stops
Zone 2: 205 stops
Zone 3: 1234 stops
...
Total stops across all zones: 32063
Feed version SHA-256: a3f42c1e8b9d7e6f5c4b3a2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3
Merged 625 stop-mode duplicates: 32063 -> 31438
core.stop: upserted 31438 rows
ops.feed_version: recorded metadata for a3f42c1e8b9d...
```

---

## Testing

Each loader has a corresponding test file:

- `test_loader_geo.py` — Geometry validation, CRS conversion
- `test_loader_census.py` — Population parsing, pseudo-SA1 handling
- `test_loader_gtfs.py` — Mode resolution, stop deduplication, geometry creation
- `test_loader_feed_version.py` — Metadata upsert, singleton active_version

Run all:
```bash
pytest backend/tests/test_loader_*.py -v
```

---

## Edge Cases & Known Issues

### GTFS Stops

1. **Name collisions:** 45 stops have identical names but different stop_ids in the same zone (e.g., "Station" appears in multiple suburbs). Not deduplicated because they are physically distinct.

2. **Dual-mode stops:** 358 stops serve two modes (tram + bus, coach + bus). Each mode pair has its own row; the two rows have identical coordinates but are separate for scoring (different catchments, frequencies).

3. **Platform vs. Station:** `location_type` is preserved (0=platform, 1=station) but not used during load. README 5.4 §4 documents filtering rationale.

### Census

1. **Pseudo-SA1s:** 4 synthetic SA1s with population = 0 (used by ABS for confidentiality). Excluded from population totals but kept in `core.census_sa1` for referential integrity.

2. **Missing SA1s:** If a real SA1 has no Census record, it is not loaded; this is caught by the Census join gate during Airflow validation.

---

## See Also

- [README §3.2](../README.md#32-geometry-as-single-source-of-position) — Why geometry is the only position representation
- [README §4.3](../README.md#43-stops-service-aggregation) — Why platform deduplication matters
- [README §5.2](../README.md#52-multizone-gtfs-structure) — Zone folder structure and GTFS variants
- [app/study_area.py](../app/study_area.py) — How study area filtering is applied at compute time
