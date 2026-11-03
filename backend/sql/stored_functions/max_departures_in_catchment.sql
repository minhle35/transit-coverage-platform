-- Function 3: max_departures_in_catchment() — FREQUENCY
-- What's the best service frequency I can access within my catchment?
--
-- For a given origin point, time window (day_type + hour), and catchment radius,
-- returns the maximum departures/hour across all stops in that catchment. This captures
-- the key insight: accessibility is defined by frequency, not proximity alone. A stop
-- 500m away with 15 departures/hour is more useful than a stop 100m away with 1/hour.
--
-- Returns: Single integer (max departures/hour), or NULL if no service data exists.
-- Joins stop geometry with stop_service_hourly table; uses GiST index for spatial filtering.
-- See doc_PostGIS_Spatial_Core.md section 3 for context.

CREATE OR REPLACE FUNCTION core.max_departures_in_catchment(
    p_origin_geom GEOMETRY,
    p_radius_m FLOAT,
    p_mode VARCHAR,
    p_feed_version VARCHAR,
    p_day_type VARCHAR,
    p_hour SMALLINT
)
RETURNS INTEGER
LANGUAGE SQL
STABLE
LEAKPROOF
AS $$
    SELECT MAX(ssh.departures)
    FROM core.stop_service_hourly AS ssh
    INNER JOIN core.stop AS s ON (
        s.feed_version_id = ssh.feed_version_id
        AND s.stop_id = ssh.stop_id
    )
    WHERE
        p_origin_geom IS NOT NULL
        AND p_feed_version IS NOT NULL
        AND p_radius_m IS NOT NULL
        AND p_radius_m > 0
        AND ssh.feed_version_id IS NOT NULL
        AND ssh.feed_version_id = p_feed_version
        AND s.mode IS NOT NULL
        AND s.mode = p_mode
        AND ssh.day_type IS NOT NULL
        AND ssh.day_type = p_day_type
        AND ssh.hour IS NOT NULL
        AND ssh.hour = p_hour
        AND ST_DWithin(s.geom, p_origin_geom, p_radius_m);
$$;

COMMENT ON FUNCTION core.max_departures_in_catchment(
    GEOMETRY, FLOAT, VARCHAR, VARCHAR, VARCHAR, SMALLINT
) IS
'Find the maximum hourly departures across all stops within a catchment.

Args:
  p_origin_geom: GEOMETRY (POINT, EPSG:7899) - origin (e.g., SA1 centroid)
  p_radius_m: FLOAT - catchment radius in metres (typically 400 or 800; must be > 0)
  p_mode: VARCHAR - transport mode (rail, tram, bus, coach)
  p_feed_version: VARCHAR - feed version ID (from ops.feed_version.feed_version_id)
  p_day_type: VARCHAR - day type (weekday, saturday, sunday)
  p_hour: SMALLINT - hour of day (0-23, typically 8 for morning peak)

Returns:
  INTEGER - maximum departures/hour within the catchment.
  NULL if no stops match, no service data exists, or inputs are invalid.

Performance:
  GiST index filters stops by location (ST_DWithin).
  Hash join on (feed_version_id, stop_id) to service_hourly.
  O(k log n) where k is stops in catchment; typically < 100 stops.

Design rationale:
  User perspective: You choose the stop with the best service within your reach.
  MAX() captures this: we report the best-case frequency available.
  Aggregate: If 3 stops exist in 400m radius with 10, 6, 2 departures/hour respectively,
  the accessible frequency is 10 (go to that stop), not 6 (average) or 2 (worst).
  Time dimension: Service varies by day_type (weekday vs weekend) and hour (peak vs off-peak).
  This query captures that variance for precise accessibility scoring.

Edge cases:
  - NULL origin_geom: NULL return
  - NULL or ≤ 0 radius_m: NULL return
  - NULL feed_version, mode, day_type, or hour: NULL return
  - No stops in catchment: NULL return (MAX over empty set)
  - Stops in catchment but no service data: NULL return (no matching rows to aggregate)
  - All service records with NULL departures: NULL return (edge case, unlikely)

Typical usage (from metrics materialization job):
  For each SA1 and each (day_type, hour) combination, compute the best accessible
  frequency. Store in marts.sa1_accessibility as max_deps_hr_400m (for bus/tram)
  or max_deps_hr_800m (for rail).
';
