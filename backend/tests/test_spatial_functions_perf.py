from sqlalchemy import text


# Command: pytest tests/test_spatial_functions_perf.py --tb=short
def test_nearest_stop_by_mode_latency(session, benchmark):
    """Nearest-neighbor query should use GiST index, ~1ms."""
    query = text("""
        SELECT * FROM core.nearest_stop_by_mode(
            ST_GeomFromText('POINT(2455250 2418000)', 7899),
            'tram',
            :feed_version
        )
    """)

    result = benchmark(
        lambda: session.execute(
            query,
            {
                "feed_version": "45bc616b049bcaf169f8703f17520cf212cc16e8f3b480d26998ead6c6bf72ad"
            },
        ).fetchone()
    )
    assert result is not None
    # benchmark will report: ~0.5-2ms if index is used, ~50ms if full scan


def test_stops_within_radius_latency(session, benchmark):
    """Range query should return in <5ms."""
    query = text("""
        SELECT * FROM core.stops_within_radius(
            ST_GeomFromText('POINT(2515884.7823238275 2390262.569348505)', 7899),
            1500, 
            'rail',
            :feed_version
        )
    """)

    result = benchmark(
        lambda: list(
            session.execute(
                query,
                {
                    "feed_version": "45bc616b049bcaf169f8703f17520cf212cc16e8f3b480d26998ead6c6bf72ad"
                },
            ).fetchall()
        )
    )
    assert len(result) > 0
