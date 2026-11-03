from sqlalchemy import text


# command: pytest tests/test_spatial_index.py --tb=short
def test_nearest_stop_uses_gist_index(session):
    """Verify EXPLAIN ANALYZE shows GiST index scan."""
    explain = session.execute(
        text("""
        EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
        SELECT * FROM core.nearest_stop_by_mode(
            ST_GeomFromText('POINT(2455250 2418000)', 7899),
            'tram',
            '45bc616b049bcaf169f8703f17520cf212cc16e8f3b480d26998ead6c6bf72ad'
        )
    """)
    ).fetchall()

    plan = explain[0][0][0]
    plan_str = str(plan)

    # If GiST is used, should see "Index Scan" in plan
    assert "Index Scan" in plan_str or "Index" in plan_str, (
        f"Full table scan detected! Plan: {plan_str}"
    )

    # If full scan: "Seq Scan" instead of "Index Scan"
    assert "Seq Scan" not in plan_str, (
        "GiST index not being used — queries will be slow!"
    )
