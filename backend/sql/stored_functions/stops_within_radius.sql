-- Function 2: stops_within_radius() — COVERAGE
-- How many stops can I reach within a walking distance?
--
-- For a given origin point and catchment radius, returns all stops of a specific mode
-- within that distance, ordered by distance. This enables coverage analysis: having
-- multiple options within walking distance is more resilient than relying on a single stop.
--
-- Returns: Set of stops (not limited to 1), all within the specified radius.
-- Uses ST_DWithin with GiST index for efficient range queries.
-- See doc_PostGIS_Spatial_Core.md section 2 for context.

CREATE OR REPLACE FUNCTION core.stops_within_radius(
    p_origin_geom GEOMETRY,
    p_radius_m FLOAT,
    p_mode VARCHAR,
    p_feed_version VARCHAR
)
RETURNS TABLE (
    stop_id VARCHAR,
    distance_m FLOAT,
    stop_name VARCHAR,
    geom GEOMETRY,
    geom_4326 GEOMETRY
)
LANGUAGE SQL
STABLE
LEAKPROOF
AS $$
    SELECT
        s.stop_id,
        ST_Distance(s.geom, p_origin_geom) AS distance_m,
        s.stop_name,
        s.geom,
        s.geom_4326
    FROM core.stop AS s
    WHERE
        p_origin_geom IS NOT NULL
        AND p_feed_version IS NOT NULL
        AND p_radius_m IS NOT NULL
        AND p_radius_m > 0
        AND s.feed_version_id IS NOT NULL
        AND s.feed_version_id = p_feed_version
        AND s.mode IS NOT NULL
        AND s.mode = p_mode
        AND ST_DWithin(s.geom, p_origin_geom, p_radius_m)
    ORDER BY ST_Distance(s.geom, p_origin_geom) ASC;
$$;

COMMENT ON FUNCTION core.stops_within_radius(GEOMETRY, FLOAT, VARCHAR, VARCHAR) IS
'Find all stops within a catchment radius of an origin point for a given mode.

Args:
  p_origin_geom: GEOMETRY (POINT, EPSG:7899) - origin location (e.g., SA1 centroid)
  p_radius_m: FLOAT - catchment radius in metres (must be > 0); mode-specific:
              rail = 800m (acceptable walking distance for frequent service)
              tram/bus = 400m (denser networks, shorter comfortable walk)
  p_mode: VARCHAR - transport mode (rail, tram, bus, coach)
  p_feed_version: VARCHAR - feed version ID (from ops.feed_version.feed_version_id)

Returns:
  SETOF TABLE with columns: stop_id, distance_m, stop_name, geom (7899), geom_4326
  Ordered by ascending distance. Empty set if no stops match or inputs invalid.

Performance:
  Uses GiST index on core.stop.geom via ST_DWithin().
  ST_DWithin is faster than computing distances for all candidates.
  O(k log n) where k is stops in radius (typically < 100, rarely > 500).

Design rationale:
  Resilience: Multiple stops within catchment > relying on single nearest stop.
  Redundancy: If one stop breaks down, others remain accessible.
  Accessibility: Supports population-weighted coverage counts (e.g., "how many SA1s
  have 3+ bus stops within 400m?").

Edge cases:
  - NULL origin_geom: empty result set
  - NULL or ≤ 0 radius_m: empty result set
  - NULL feed_version or mode: empty result set
  - No stops in catchment: empty result set (correct behavior)
  - Large radius (5000+ m): may return all stops (unfiltered if all match)
';
