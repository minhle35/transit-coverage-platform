## Architectural Context
The platform operates with several key invariants, implemented in ```geo.py```, ```census.py```, ```gtfs.py``` in the ```app/models``` in the previous stage:

- Dual-CRS principle: EPSG:7899 (metric, for distance calculations) + EPSG:4326 (WGS84, for GeoJSON)
- Idempotent operations: All loads use ON CONFLICT clauses, safe to recompute
- Explicit identifier carries: No positional joins; feed_version_id, sa1_code flow through all layers
- One framework: PostGIS owns all authoritative geometries and spatial indexes
- Versioning: Results carry feed_version_id (from ops.active_version) and optional model_run_id

--

In this design, we will build on this by materializing distance metrics and accessibility aggregations so the API can query them efficiently without recomputing spatial joins on every request.


### Core Question to Answer: "Which SA1s have good transit access?"

##### Deliverables:

- Closest-stop distances by mode for each SA1 (meterological distance + mode)
- Stop density metrics per SA1 (counts within catchment radii)
- Population-weighted accessibility aggregates (SA1 representative points)
- Idempotent batch computation jobs (safe to rerun with same feed)
- SQL functions for reusable spatial logic
- Efficient indexes for API queries
- Test coverage for spatial correctness

- Phase 1.1: Schema Extensions — Spatial Metrics Tables
- Objective: Add tables to store computed accessibility metrics, indexed for API queries.

Files to Create:

- Alembic Migration
- Creates three new tables in core schema:
  -  sa1_stop_distance: Closest stop of each mode per SA1
  -  sa1_accessibility: Aggregated accessibility metrics per SA1
  -  sa1_coverage_zone: Coverage zone membership (which SA1s are within mode catchments)
- SQL functions: spatial operations in PostGIS 
- Test files
- API layer: read views and endpoints
- Integration & Orchestration: wire the metrics job into the data pipeline

## Key decisions:
### 1. Raw PostGIS SQL Functions vs GeoPandas and Shapely vs ORM-only (SQLAlchemy + GeoAlchemy2)
After running ```scripts/data_viz.py``` + data exploration: we understand there are 15,482 VIC SA1 origins (from shapefiles) and 32,063 transit stops (from gtfs schedules).
Hence if we use ```GeoPandas``` Python
- 15,000 iterations 
- each iteration: compute distance to 32k points
- 15k * 32k = 480m distance calculations
- Shapely distance: can do 0.5-1 microseconds per call (GEOS library)
- 480M * 1 microsecond = 480 seconds = 8 minutes (math, I/O overhead)
- Memory: ~500MB for geometries + temporaru lists
- Total: 8-10 minutes, single-threaded

If we use ```PostGIS``` with GiST Index, we can build index on ```stop.geom``` (balanced tree indexing for geometric and spatial data)
- for each SA1 point, query uses index to find 30-50 stops within 400m (not 32K)
- we only need to compute distance to those 50 stops
- 480M calculations become 50K index-filtered calculations
- 50K * 1 microseconds = 50 milliseconds
- 9600x faster than using ```GeoPandas``` with Python code

Reasons:
- We can't index in GeoPandas at query time
- GeoPandas can create a spatial index (RTree) but it will only for data already exist in memory
- Queries like "stops within 400m" needs to prune candidates before computing distance
- PostGIS GiST indexes live on disk; they're consulted automatically by the query planner