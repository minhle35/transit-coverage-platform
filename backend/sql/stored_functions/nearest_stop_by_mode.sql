CREATE OR REPLACE FUNCTION core.nearest_stop_by_mode(
    p_origin_geom GEOMETRY,
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
        AND s.feed_version_id IS NOT NULL  
        AND s.feed_version_id = p_feed_version
        AND s.mode IS NOT NULL            
        AND s.mode = p_mode
    ORDER BY s.geom <-> p_origin_geom
    LIMIT 1;
$$;
