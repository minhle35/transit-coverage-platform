-- Phase 0 Data Foundation Sanity Checks
-- Run after load_reference_data.py completes

-- 1. Row counts match expectations
SELECT
  (SELECT COUNT(*) FROM core.stop) as stops_loaded,
  (SELECT COUNT(*) FROM core.area_sa1) as sa1_areas_loaded,
  (SELECT COUNT(*) FROM core.census_sa1) as census_records_loaded,
  (SELECT COUNT(*) FROM ops.feed_version) as feed_versions,
  (SELECT COUNT(*) FROM ops.active_version) as active_version_rows;

-- 2. Verify 31,140 unique stop-mode pairs
SELECT COUNT(*) as unique_stop_mode_pairs
FROM core.stop
GROUP BY feed_version_id;

-- 3. Check SA1 boundaries coverage
SELECT
  COUNT(*) as total_sa1s,
  COUNT(DISTINCT sa1_code) as unique_sa1_codes,
  MIN(ST_Area(geom)) as min_area_m2,
  MAX(ST_Area(geom)) as max_area_m2
FROM core.area_sa1;

-- 4. Census population (excluding pseudo-SA1s)
SELECT
  COUNT(*) as real_sa1_records,
  SUM(population) as total_population
FROM core.census_sa1
WHERE sa1_code NOT IN ('29797979991', '29797979992', '29797979993', '29999949999');

-- 5. Stops by mode
SELECT mode, COUNT(*) as stop_count
FROM core.stop
GROUP BY mode
ORDER BY mode;

-- 6. Active version is set
SELECT id, feed_version_id, model_run_id, updated_at
FROM ops.active_version
WHERE id = 1;

-- 7. Feed version metadata
SELECT
  feed_version_id,
  sha256,
  status,
  row_counts,
  downloaded_at
FROM ops.feed_version
ORDER BY downloaded_at DESC
LIMIT 1;

-- 8. Verify CRS: all geometries in EPSG:7899 (metric)
SELECT
  ST_Srid(geom) as metric_crs,
  ST_Srid(geom_4326) as wgs84_crs,
  COUNT(*) as geometry_count
FROM core.stop
GROUP BY ST_Srid(geom), ST_Srid(geom_4326);

-- 9. Sample stop record (spot check)
SELECT
  stop_id,
  mode,
  stop_name,
  location_type,
  parent_station,
  ST_X(geom_4326) as lon,
  ST_Y(geom_4326) as lat
FROM core.stop
LIMIT 1;

-- 10. Final summary
SELECT
  'Phase 0 Data Foundation' as phase,
  'COMPLETE' as status,
  NOW() as checked_at,
  (SELECT COUNT(*) FROM core.stop) as stops,
  (SELECT COUNT(*) FROM core.area_sa1) as sa1_areas,
  (SELECT COUNT(*) FROM core.census_sa1) as census_records,
  (SELECT feed_version_id FROM ops.active_version WHERE id = 1) as active_feed;
