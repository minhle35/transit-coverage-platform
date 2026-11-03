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

## Design functions to build SQL functions for metrics

We later will compute the score function
```
score = (
  distance_decay(closest_rail_m) + catchment_bonus(rail_within_800m) + frequency_weight(max_depth_hr_400m)
)
```
we need to prepare the functions to compute distance to the nearest stop, how many within reach, what's best frequency.

In other words, we want to capture:
- is transit reachable? (distance)
- is transit resilient? (coverage/redundancy)
- is service frequent? (frequency)

#### 1. Distance -  How far away is the closest stop?
Distance is a function of (sa1_centroid, 'rail', feed_version)
-> Returns: stop_id = "stop_123", distance_m = 750

- This is a foundational metric to understand/measure accessibility later
- Different modes have different walkability (rail: 800m acceptable, tram: 400m)
- We need to answer this question: "Is my neighborhood walkable to transit at all?"

##### First we find a random location to make it as our current location
```
-- Get 5 random SA1s from Melbourne CBD area
SELECT 
    sa1_code,
    sa2_name,
    ST_AsText(ST_Centroid(geom)) AS centroid_7899,
    ST_AsText(ST_Transform(ST_Centroid(geom), 4326)) AS centroid_latlon
FROM core.area_sa1
WHERE gcc_code = '2GMEL' # Great Melbourne
ORDER BY RANDOM()
LIMIT 5;

```
- we use `ST_AsText` to converts a spatial geometry object into its Well-Known Text (WKT) string representation (e.g., POINT(144.96 -37.81)), making it human-readable
- `ST_Centroid()` to compute the geometric center (centroid) of the given geometry (geom)

Result - we choose one of them for an example
```
  sa1_code   |          sa2_name           |                centroid_7899                 |                centroid_latlon                
-------------+-----------------------------+----------------------------------------------+-----------------------------------------------
 21204156514 | Keysborough - North         | POINT(2515884.7823238275 2390262.569348505)  | POINT(145.18082620963267 -37.98870718225923)
 20802142713 | Bentleigh East - South      | POINT(2505756.8189697284 2396395.771924024)  | POINT(145.06548544005065 -37.933568424334354)
 21201155201 | Pakenham - South West       | POINT(2538546.442417804 2380687.372732103)   | POINT(145.43929816404884 -38.07430631486971)
 20903121408 | Research - North Warrandyte | POINT(2519131.0622909167 2419461.8914679517) | POINT(145.2170227459051 -37.725564533100425)
 21204146004 | Noble Park - West           | POINT(2515404.824148035 2392356.5644168435)  | POINT(145.17531866604725 -37.96984969987287)
(5 rows)

```

- We can use convert into lat/lon by using
```
SELECT ST_AsText(
    ST_Transform(
        ST_GeomFromText('POINT(XXXXXXX YYYYYYY)', 7899),
        4326  -- Convert to lat/lon (WGS84)
    )
) AS latlon;

```
For example:
```
SELECT ST_AsText(
    ST_Transform(
        ST_GeomFromText('POINT(2515884.7823238275 2390262.569348505)', 7899),
        4326  -- Convert to lat/lon (WGS84)
    )
) AS latlon;
```

##### Second, we get only the CLOSEST stop
```
EXPLAIN ANALYZE
SELECT 
  stop_id, 
  stop_name, 
  geom, 
  ST_Distance(geom, ST_GeomFromText('POINT(2515884.7823238275 2390262.569348505)', 7899)) AS distance_m
FROM core.stop
WHERE mode = 'tram'
ORDER BY distance_m ASC
LIMIT 1;
```

Result:
```
 stop_id |                   stop_name                   |                        geom                        |     distance_m     
---------+-----------------------------------------------+----------------------------------------------------+--------------------
 21127   | Vermont South Shopping Centre/Burwood Hwy #75 | 0101000020DB1E00004F8BB6EA193243414E65352527594241 | 14680.342557173759
(1 row)
```

**This answers the question: What's the single closet tram stop from the given location**

##### Third, we can use `<->` operator for speed
We can add `feed_version` filtering for some purposes like
- loading: know which feed is current
- query: filter to only current feed's stops
- scoring: ensure scores match the feed used
- history: track which feed produced which score
- rollback: switch back to previous feed if needed


```
EXPLAIN ANALYZE
SELECT
    stop_id,
    stop_name,
    geom,
    ST_Distance(geom, ST_GeomFromText('POINT(2515884.7823238275 2390262.569348505)', 7899)) AS distance_m
FROM core.stop
WHERE
  mode = 'tram'
  AND feed_version_id = '45bc616b049bcaf169f8703f17520cf212cc16e8f3b480d26998ead6c6bf72ad'

ORDER BY geom <-> ST_GeomFromText('POINT(2515884.7823238275 2390262.569348505)', 7899)
LIMIT 1;
```

- **Query to get feed_version_id**

```
SELECT feed_version_id FROM ops.active_version WHERE id = 1;
```

##### Fourth, parametrize it (function argument)
- Turn this into reusable function where we pass the origin, mode, feed_version

```
CREATE OR REPLACE FUNCTION core.nearest_stop_by_mode(
  p_origin_geom GEOMETRY,
  p_mode VARCHAR,
  p_feed_version VARCHAR
)
RETURNS TABLE(
  stop_id VARCHAR,
  distance_m FLOAT,
  stop_name VARCHAR,
  geom GEOMETRY,
  geom_4326 GEOMETRY
)
LANGUAGE SQL
STABLE LEAKPROOF
AS $$
  SELECT
        s.stop_id,
        ST_Distance(s.geom, p_origin_geom) AS distance_m,
        s.stop_name,
        s.geom,
        s.geom_4326
    FROM core.stop AS s
    WHERE
        s.mode = p_mode
        AND s.feed_version_id = p_feed_version
    ORDER BY s.geom <-> p_origin_geom
    LIMIT 1;
$$
```

**Last few steps: save the SQL function file and call it in alembic version file **
```
Step 1:
Write the function in sql/your_function.sql.
Step 2:
Generate the migration file using the command
Step 3:
Open the generated file and add the single line to read and execute your .sql file
Step 4:
Run the migration
alembic upgrade head
```


##### Check the function after migration
- Connect to the database (via docker)
- in psql use these command: `\df` core.nearest_stop_by_mode
- SQL query to access the built-in system view to view the metadata about stored functions, procedures, methods
```
SELECT routine_name, routine_type, routine_definition
FROM information_schema.routines
WHERE routine_schema = 'core'
AND routine_name = 'nearest_stop_by_mode';
```

- Test on real data point
```

SELECT * FROM core.nearest_stop_by_mode(
  ST_GeomFromText('POINT(2515884.7823238275 2390262.569348505)', 7899),
  'tram',
  '45bc616b049bcaf169f8703f17520cf212cc16e8f3b480d26998ead6c6bf72ad'
);

2. 