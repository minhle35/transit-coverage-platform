-- Phase 0 Cleanup: Truncate tables for fresh load
-- Use this to reset state before running load_reference_data.py fresh

TRUNCATE TABLE core.stop CASCADE;
TRUNCATE TABLE core.area_sa1 CASCADE;
TRUNCATE TABLE core.census_sa1 CASCADE;
TRUNCATE TABLE ops.feed_version CASCADE;
TRUNCATE TABLE ops.active_version CASCADE;

-- Reset sequences if any
ALTER SEQUENCE IF EXISTS ops.active_version_id_seq RESTART WITH 1;

-- Verify all tables are empty
SELECT 'core.stop' as table_name, COUNT(*) FROM core.stop
UNION ALL SELECT 'core.area_sa1', COUNT(*) FROM core.area_sa1
UNION ALL SELECT 'core.census_sa1', COUNT(*) FROM core.census_sa1
UNION ALL SELECT 'ops.feed_version', COUNT(*) FROM ops.feed_version
UNION ALL SELECT 'ops.active_version', COUNT(*) FROM ops.active_version;
