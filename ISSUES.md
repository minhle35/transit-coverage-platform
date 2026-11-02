# Issue register

Known defects, gaps and decisions outstanding, as of 2 November 2026. Each entry
states the evidence, the blast radius, and what closing it requires. Phase
numbers refer to `drafts/plans.md`.

Severity: **B** blocks the next phase · **C** correctness risk · **H** hygiene.

---

## Migration history

### I-19 · C · Half the migrations are untracked in git, and the chain has no replay test

**Resolved:** the chain was briefly unusable — `alembic current` failed with
`Can't locate revision identified by 'b9fd3f3cc713'` because four migration
files were absent. They have been restored (one recovered from a dangling git
blob, `d36cd9e5f9f050168a1a56ce758fffd7bedf3ca4`). The history is now linear
across eight revisions:

    ab32b700b938  initial schema
    8b1fcac40ce6  add gtfs and reference geography tables
    0262c49c3417  drop route/trip/servicecalendar/serviceexception for tier 1
    cec7929d5af7  add spatial metrics tables
    06e1d0060596  add mode column to stop, populate from zone
    5ba4d9ba9d52  widen_stop_ids  (also drops parent_station, level_id,
                                   wheelchair_boarding, is_station -- see I-06)
    2841096a513b  widen_stop_ids
    b9fd3f3cc713  stop mode: three-value scoring vocabulary, part of PK  (head)

`alembic current` resolves to head and `alembic check` reports no new upgrade
operations, so the models and the live database agree.

**What remains, and it is the actual root cause.** Four of the eight migrations
are untracked:

    UNTRACKED  20261102_06e1d0060596_add_mode_column_to_stop_populate_from_.py
    UNTRACKED  20261102_2841096a513b_widen_stop_ids.py
    UNTRACKED  20261102_5ba4d9ba9d52_widen_stop_ids.py
    UNTRACKED  20261102_b9fd3f3cc713_stop_mode_three_value_scoring_.py

Untracked files are invisible to `git status` summaries and to every safety net
git provides, which is how they went missing. Until they are committed, the
schema cannot be reproduced from a clone: a fresh database would stop at
`cec7929d5af7`, with no `mode` column on `core.stop`, no three-value check
constraint, and a two-column primary key.

**Two smaller problems in the restored set.** `5ba4d9ba9d52` and `2841096a513b`
are both titled `widen_stop_ids` while doing different things — the first also
drops four columns, which is where I-06's `parent_station` went. And
`alembic check` only proves the models match *this* database; it does not prove
the chain replays from empty, which is the property that was actually violated.

**Closing it:**

1. Commit the four untracked migrations. Nothing else is safe until this is done.
2. Rename the two `widen_stop_ids` revisions to describe what they each do.
3. Add a CI step that runs `alembic upgrade head` against an empty database and
   asserts the result matches `Base.metadata` — a replay test, not a diff
   against a database that is already correct. That is what would have caught
   this.
4. Optionally verify the replay locally once by dropping `core`, `marts` and
   `ops` and running `alembic upgrade head` from scratch. This also clears the
   571 stale rows in I-09, so the two are worth doing together.

## Blocking Phase 1 completion

### I-01 · B · `ops.feed_version` is never written, and the metric tables require it

`core.sa1_stop_distance` and `core.sa1_accessibility` both carry
`FOREIGN KEY (feed_version_id) REFERENCES ops.feed_version(feed_version_id)`,
and `ops.feed_version` has **0 rows**. Any attempt to populate either table
fails on the foreign key.

The GTFS loader computes a `feed_version_id` (SHA-256 of the newest
`google_transit.zip`) and stamps it onto every stop row, but never records the
version itself. `core.stop.feed_version_id` has no FK, which is why that load
succeeds and masks the problem.

**Closing it:** a `ops.feed_version` upsert in the loader, before stops, writing
`feed_version_id`, `source_url`, `sha256`, `status='loaded'` and `row_counts`.
`ops.active_version` then needs its single row. Both are prerequisites for the
atomic promotion in Phase 4 (README 7.5).

### I-02 · B · The Phase 1 spatial functions were never written

The tables exist and are empty. `core.nearest_stop_by_mode`,
`core.stops_within_radius` and `core.max_departures_in_catchment` are specified
but absent, and there is no `app/queries/` package — `drafts/plans.md` Phase 1
calls for `app/queries/proximity.py` so that SQL is not scattered as strings.

**Closing it:** the three functions in a migration, a thin
`app/queries/proximity.py` wrapper, and the Phase 1 "done when" test (two points
a known 500 m apart, asserting `ST_Distance` within 1 m).

### I-03 · C · Metric tables sit in `core`, but README 7.4 assigns derived results to `marts`

README 7.4 reserves `core` for "versioned, conformed entities" and `marts` for
"published results" read by API views. `sa1_stop_distance` and
`sa1_accessibility` are derived results, so they belong in `marts`. Leaving them
in `core` means the API would read `core` directly, breaking the single read
path the architecture depends on.

Compounding it, `drafts/plans.md` names different tables again
(`core.sa1_stop_proximity`, `marts.accessibility_score`). Three names for two
tables.

**Closing it:** decide the naming, move the tables to `marts`, and reconcile the
plan, the README and the models so one name survives.

---

## Blocking Phase 2 (scoring)

### I-04 · B · No departure data: `core.stop_service_hourly` has a model but no loader

This is the largest gap. README 4.5's formula is

    A_i = Σ w_m · min(f_s, f_cap) · e^(−β_m · d_is)

and `f_s` — scheduled departures per hour — has no source. The table is empty
and nothing writes it, so **the scoring model cannot be evaluated at all**.

Harder than it looks, for three reasons:

1. `stop_times.txt` is 649 MB in the bus feed. README 7.4 forbids storing it
   ("Raw stop times are never stored"), so it must be streamed in chunks and
   discarded, keeping only per-stop/hour/day-type counts.
2. `day_type` requires resolving `trips.txt` → `calendar.txt` and
   `calendar_dates.txt`. The `Route`, `Trip`, `ServiceCalendar` and
   `ServiceException` models were **dropped** during Phase 0 simplification, so
   these must be read transiently rather than joined in SQL.
3. `departure_time` can exceed `24:00:00` for after-midnight service (see I-11).

**Closing it:** `app/loaders/service.py` — stream `stop_times.txt`, resolve day
type through trips and calendars in memory, aggregate to
`(feed_version_id, stop_id, day_type, hour) → departures`, and count only
`pickup_type = 0` departures per README 4.3.

### I-05 · B · No `transitcov` package, which README 3.4 and 7.2 both promise

README commits to "an installable Python library, `transitcov`, containing the
scoring and GTFS logic as pure, testable functions", explicitly free of any
database or web framework (3.4: "`transitcov` must not depend on a database or a
web framework"). Everything currently lives under `app/`, which imports
SQLAlchemy throughout.

**Closing it:** a separate top-level package with its own `pyproject.toml`,
holding the scoring formula and GTFS parsing as pure functions over
DataFrames. `app/` keeps the DB-bound orchestration and calls into it. Without
this split the golden-file and property tests in README 4.10 need a live
database, which defeats their purpose.

### I-06 · RESOLVED · `parent_station` restored

Migration `bc33e4cdbabe` brings the column back, so README 4.3's merge of
platforms under one parent per mode is possible again. 212 of the loaded rows
carry a parent, resolving to 13 distinct stations in the CBD study area.

The merge itself is still Phase 2 work (it belongs in the frequency
aggregation, not the stop loader), but the data it needs is now present.

## Blocking Phase 3 (equity)

### I-07 · B · SA2 boundaries are still not downloaded

README 4.8 defines `marts.coverage_sa2` and 1.3 promises "population-weighted
roll-ups to SA2". 5.3 records that 119 SA2 Census CSVs are present but the SA2
**boundary** file is not. 5.5 lists it as required before a full run.

**Closing it:** download ASGS Edition 3 SA2 boundaries (matching the 2021
Census, per the Edition 3 decision in I-13), add `core.area_sa2` and a loader.

### I-08 · H · The Phase 3 plan still routes through `sa1_correspondence`, which no longer exists

`drafts/plans.md` Phase 3 says to join Census "via `sa1_correspondence`". That
table was dropped when the project moved to 2021 ASGS Edition 3 boundaries,
which match the 2021 Census exactly — `core.area_sa1.sa1_code` joins
`core.census_sa1.sa1_code` directly at 15,478/15,482.

**Closing it:** correct the plan. No code change.

---

## Pipeline correctness

### I-09 · C · The loaders have no delete path, so narrowing scope leaves orphans

`core.stop` holds **1,223 rows, of which 571 fall outside the Melbourne CBD
study area** — residue from statewide loads that ran before the CBD filter was
added. Verified by `ST_Within` against the CBD SA2 polygons: 652 inside
(rail 224, bus 242, tram 186), 571 outside.

Every loader upserts via `ON CONFLICT DO UPDATE` and never deletes. Because both
loads share one `feed_version_id` (the same ZIP), there is no version boundary
to filter the stale rows out by. Those 571 stops would be matched as "nearest
stop" by SA1s whose catchments they should never enter, silently corrupting
every Phase 1 metric.

**Closing it:** short term, truncate and reload. Properly, this is what README
7.5's atomic promotion exists to prevent: load into `staging` under a new
`feed_version_id`, validate, then swap `ops.active_version` in one transaction.
Phase 4 work, but the truncate cannot wait for it.

### I-10 · C · Study-area scope is applied asymmetrically across loaders

`gtfs.extract()` filters stops to the eleven Melbourne CBD SA2s, but the
geography and Census loaders load all of Victoria: 15,478 SA1s and 15,482 Census
rows against 652 stops. Phase 1 would therefore compute "distance to nearest
stop" for ~15,000 SA1s whose nearest in-scope stop is tens of kilometres away,
producing a table that is 96% meaningless rows.

**Closing it:** one study-area definition, applied by every loader — a shared
`app/study_area.py` holding the SA2 name list (currently duplicated between
`loaders/gtfs.py` and `scripts/data_viz.py`), or better, the GCCSA code `2GMEL`
that README 5.5 already names.

### I-11 · C · After-midnight departure times are not yet handled

README 5.4 flags it: `departure_time` can exceed `24:00:00`, and parsing it as a
clock time silently drops late-night service or throws. No parsing code exists
yet, so this is a trap waiting for I-04 rather than a present defect. Times must
be read as durations from midnight.

### I-12 · C · Replacement buses are not excluded

README 5.4 requires dropping `R-Bus` platform codes, which metro feeds use for
disruption replacement services. `platform_code` is loaded but never filtered,
so once I-04 lands, replacement services will be counted as scheduled service.

### I-13 · H · Two SA1 boundary vintages are present on disk

`data/` holds both `SA1_2021_AUST_SHP_GDA2020` and `SA1_2026_AUST_SHP_GDA2020`.
The project loads 2021 (Edition 3) to match the 2021 Census exactly, and
`loaders/geo.py` auto-detects the edition from column names, so the 2026 set is
unused. Harmless but confusing, and the edition-detection branch for 2026 is
dead code covered by tests.

---

## Hygiene

### I-14 · RESOLVED · The two failing tests now pass

`18 passed`. `test_transform_materializes_location_type_flags` became
`test_transform_preserves_location_type`, asserting `location_type` passes
through and that no derived flag is emitted;
`test_transform_handles_null_wheelchair_boarding` works again now the column is
back, and additionally asserts the value is an `int` rather than the float the
feed supplies. `test_transform_preserves_zone_field` became
`test_transform_resolves_mode_and_drops_zone`.

### I-15 · RESOLVED · Commented-out columns removed

`models/gtfs.py` and `loaders/gtfs.py` no longer carry commented-out column
definitions. `parent_station` and `wheelchair_boarding` came back properly (see
I-06); `level_id` and `is_station` are gone for good.

### I-16 · RESOLVED · `zone` dropped

Migration `bc33e4cdbabe` removes it. The folder is an operational branch rather
than a mode (README 5.2): it resolves `mode` during load and carries nothing
afterwards, and post-dedup it was lossy anyway, recording one contributing
branch of several. Provenance is the archived ZIP and its SHA-256 in
`ops.feed_version` (README 7.3), which is complete where the column was not.

Dropped alongside it, same migration: `stop_lat`/`stop_lon` (redundant with
`geom_4326`), `stop_code` (22% populated, and a code typed as a float), and
`is_platform` (exactly `location_type == 0`, and it encodes the wrong predicate
— README 5.4 item 4 counts platforms *and* stations, which a boolean cannot
express). `core.stop` is now ten columns, each justified by a specific README
section.

### I-17 · H · Mode is derived from directory layout when an authoritative per-stop source exists

`core.stop.mode` is derived from the zone folder, which is an operational branch
rather than a transport mode. The derivation is corroborated by `route_type` for
all eight folders, so it is correct — but it is not authoritative.

Transport Victoria's *Public Transport Stops* dataset (GeoJSON, 8 MiB,
CC BY 4.0) carries a per-stop `MODE` property with eight fixed values matching
the eight folders exactly. Its `STOP_ID` is declared `INTEGER`, which excludes
2,564 non-numeric GTFS ids — but those are 348 stations, 862 entrances and 1,351
wayfinding nodes, and only **3 platforms**, so it covers 29,499 of 29,502
platforms.

This is a cheaper route to an authoritative mode than the
`routes → trips → stop_times → stops` join over 649 MB that README 5.2
currently names for version 2. Its risk is vintage: last updated 28 July 2025
against a weekly GTFS feed, so it needs the same match-rate validation gate as
the boundary/Census join.

### I-18 · H · The study-area SA2 list is duplicated

`MELBOURNE_CBD_SA2_NAMES` in `loaders/gtfs.py` and `CBD_SA2_NAMES` in
`scripts/data_viz.py` are separate copies of the same eleven names. They will
drift. See I-10.
