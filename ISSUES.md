# Issue register

Known defects, gaps and decisions outstanding, as of 2 November 2026. Each entry
states the evidence, the blast radius, and what closing it requires. Phase
numbers refer to `drafts/plans.md`.

Severity: **B** blocks the next phase · **C** correctness risk · **H** hygiene.

---

## Migration history

### I-19 · H · The migration chain replays, but nothing enforces that it keeps doing so

**Mostly resolved.** The chain was briefly unusable -- `alembic current` failed
with `Can't locate revision identified by 'b9fd3f3cc713'` because four
migration files were absent, one of which (`06e1d0060596`) was the only
migration creating `core.stop.mode`. All were restored, one recovered from a
dangling git blob (`d36cd9e5f9f050168a1a56ce758fffd7bedf3ca4`), and all nine
are now committed.

The replay is verified, not merely assumed: the `core`, `marts`, `ops`,
`staging`, `raw` and `api` schemas were dropped, `alembic upgrade head` ran all
nine from empty, `alembic check` reported no divergence from the models, and a
full reload followed. That is the property the breakage violated and that
`alembic check` alone cannot establish -- it only compares the models against a
database that may already be correct.

    ab32b700b938  initial schema
    8b1fcac40ce6  add gtfs and reference geography tables
    0262c49c3417  drop route/trip/servicecalendar/serviceexception for tier 1
    cec7929d5af7  add spatial metrics tables
    06e1d0060596  add mode column to stop, populate from zone
    5ba4d9ba9d52  widen_stop_ids  (also drops parent_station, level_id,
                                   wheelchair_boarding, is_station -- see I-06)
    2841096a513b  widen_stop_ids
    b9fd3f3cc713  stop mode: three-value scoring vocabulary, part of PK
    bc33e4cdbabe  stop: restore parent_station and wheelchair_boarding

**What remains.** Nothing automated protects this. The replay was run by hand
once; the next broken chain will be found the same way. It needs a CI step that
runs `alembic upgrade head` against an empty database and asserts the result
matches `Base.metadata`.

Also unaddressed: `5ba4d9ba9d52` and `2841096a513b` are both titled
`widen_stop_ids` while doing different things, the first also dropping four
columns. Worth renaming so the history reads honestly.

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

### I-09 · RESOLVED · Scope moved out of the loaders

The 571 orphan rows are gone, and the cause with them. `core.stop` now holds
the whole feed -- 31,140 stop-mode pairs, 29,266 of them service-carrying --
and study-area scope is a read-time predicate instead of a load filter.

The database was also rebuilt from empty to confirm it: all nine migrations
replayed with `alembic upgrade head`, `alembic check` clean, then a full
reload. That doubled as the replay verification I-19 had never had.

Scope belonged in the wrong layer. README 7.4 defines `core` as "versioned,
conformed entities" -- the feed as received -- so filtering during load made
`core.stop` a partial record, which is exactly why narrowing it left rows with
no version boundary to filter them out by.

It was wrong numerically too, which is the stronger reason. Measured against
the full feed: 494 service-carrying stops sit inside the eleven CBD SA2s, but
**245 more sit outside the boundary within 400 m of it**, and 442 within
800 m. A stop across the boundary still serves residents inside it, so the old
filter truncated a third of the relevant 400 m supply, and nearly half the
800 m supply, for every boundary SA1.

Still open, and not fixed by this: the loaders cannot handle a *shrinking*
input. A stop removed from a future feed will linger, because the upsert has
no delete path. That is Phase 4's staging-and-promotion work (README 7.5).

### I-10 · RESOLVED · One study-area definition, applied at read time

`app/study_area.py` now holds it once. The loaders no longer disagree about
scope, because none of them filters: geography, Census and GTFS all load
everything the source publishes.

The definition also changed. The GTFS loader had been filtering to eleven
inner SA2s -- 237 SA1s and 100,256 people, about **2%** of the study area
README 1.3 and 1.4 actually commit to. The project scope is now the ABS GCCSA
code `2GMEL`, Greater Melbourne: 11,487 SA1s and 4,917,633 people, carried on
`core.area_sa1.gcc_code`. The CBD set survives as a documented development
subset for fast iteration and for `scripts/data_viz.py`, never as a load
filter.

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

### I-18 · RESOLVED · The duplicated SA2 list is gone

Both copies are replaced by `app.study_area.MELBOURNE_CBD_SA2_NAMES`.
`scripts/data_viz.py` imports it (the package is installed editable, so no
path manipulation is needed) and the GTFS loader no longer needs it at all.
