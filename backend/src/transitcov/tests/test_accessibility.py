"""Tests for accessibility scoring formula (README §4.7 worked example).

Tests verify the formulas: A_i = Σ w_m · min(f, f_cap) · exp(-β · d)
and score = 100 · (1 - exp(-A_i / k)).
"""

import math

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point
from transitcov.scoring.accessibility import (
    compute_accessibility,
    compute_coverage_scores,
    decay_rate_for_mode,
    score_from_accessibility,
)
from transitcov.scoring.params import ScoringParams


class TestDecayRate:
    """Test distance decay rate calculation."""

    def test_decay_rate_rail(self):
        """For rail (R=800m), β = 2·ln(2)/800 ≈ 0.001733 m⁻¹."""
        params = ScoringParams(r_rail=800.0, r_tram=400.0, r_bus=400.0)
        beta = decay_rate_for_mode("rail", params)
        expected = 2.0 * math.log(2) / 800.0
        assert abs(beta - expected) < 1e-8

    def test_decay_rate_tram(self):
        """For tram (R=400m), β = 2·ln(2)/400 ≈ 0.003466 m⁻¹."""
        params = ScoringParams(r_tram=400.0)
        beta = decay_rate_for_mode("tram", params)
        expected = 2.0 * math.log(2) / 400.0
        assert abs(beta - expected) < 1e-8

    def test_decay_rate_boundary(self):
        """At boundary (d = R), weight = 0.25."""
        params = ScoringParams(r_tram=400.0)
        beta = decay_rate_for_mode("tram", params)
        weight = math.exp(-beta * 400.0)
        assert abs(weight - 0.25) < 1e-4

    def test_decay_rate_half_radius(self):
        """At half radius (d = R/2), weight = 0.5."""
        params = ScoringParams(r_tram=400.0)
        beta = decay_rate_for_mode("tram", params)
        weight = math.exp(-beta * 200.0)
        assert abs(weight - 0.5) < 1e-4


class TestWorkedExample:
    """Test the worked example from README §4.7.

    One tram stop with f=6/hr, R=400m, w=1.0, k=5.0, β≈0.003466 m⁻¹.
    Expected scores: [69.9, 45.1, 25.9, 0.0] at distances [0, 200, 400, 500]m.
    """

    @pytest.fixture
    def params(self):
        """Standard parameters for worked example."""
        return ScoringParams(r_tram=400.0, w_tram=1.0, k=5.0)

    @pytest.fixture
    def origins(self):
        """Four origin points."""
        coords = [(0, 0), (200, 0), (400, 0), (500, 0)]
        points = [Point(x, y) for x, y in coords]
        return gpd.GeoDataFrame(
            {"id": [f"O{i + 1}" for i in range(4)]},
            geometry=points,
            crs=7899,
        )

    @pytest.fixture
    def stop(self):
        """One tram stop at origin with 6 departures/hour."""
        return gpd.GeoDataFrame(
            {"mode": ["tram"], "frequency": [6.0]},
            geometry=[Point(0, 0)],
            crs=7899,
        )

    def test_worked_example_scores(self, origins, stop, params):
        """Scores match expected values ±1% at each distance."""
        result = compute_coverage_scores(origins, stop, params)

        expected_scores = [69.9, 45.1, 25.9, 0.0]
        for i, expected in enumerate(expected_scores):
            actual = result.iloc[i]["score"]
            # ±1% tolerance
            assert abs(actual - expected) < 1.0, (
                f"Score at O{i + 1}: {actual} ≠ {expected}"
            )

    def test_worked_example_a_i(self, origins, stop, params):
        """Accessibility index A_i matches expected values."""
        result = compute_coverage_scores(origins, stop, params)

        expected_a_i = [6.0, 3.0, 1.5, 0.0]
        for i, expected in enumerate(expected_a_i):
            actual = result.iloc[i]["a_i"]
            # ±2% tolerance
            assert abs(actual - expected) < 0.2, (
                f"A_i at O{i + 1}: {actual} ≠ {expected}"
            )


class TestScoreProperties:
    """Test properties of the scoring function."""

    @pytest.fixture
    def params(self):
        return ScoringParams()

    def test_score_range(self, params):
        """Scores are always in [0, 100)."""
        a_i = np.linspace(0, 20, 100)
        scores = score_from_accessibility(a_i, params)

        assert np.all(scores >= 0)
        assert np.all(scores < 100)

    def test_score_monotonicity(self, params):
        """Score increases with accessibility."""
        a_i = np.array([0, 1, 2, 5, 10, 20])
        scores = score_from_accessibility(a_i, params)

        diffs = np.diff(scores)
        assert np.all(diffs > 0), "Scores must be strictly increasing"

    def test_score_saturation(self, params):
        """Score approaches 100 asymptotically."""
        a_i = np.array([100, 1000, 10000])
        scores = score_from_accessibility(a_i, params)

        # All scores should be > 90
        assert np.all(scores > 90)
        # And all scores should be <= 100 (can equal due to floating point)
        assert np.all(scores <= 100)
        # And increasing very slowly
        assert scores[-1] - scores[-2] < scores[-2] - scores[-3]

    def test_score_zero(self, params):
        """Score is 0 when accessibility is 0."""
        a_i = np.array([0])
        scores = score_from_accessibility(a_i, params)
        assert scores[0] == 0


class TestOrderIndependence:
    """Test that results are order-independent."""

    @pytest.fixture
    def data(self):
        """Create multiple origins and stops."""
        origins = gpd.GeoDataFrame(
            {"id": [f"O{i}" for i in range(5)]},
            geometry=[Point(i * 100, 0) for i in range(5)],
            crs=7899,
        )
        stops = gpd.GeoDataFrame(
            {"mode": ["tram", "bus", "rail"], "frequency": [6, 4, 8]},
            geometry=[Point(x, y) for x, y in [(0, 0), (100, 100), (200, 0)]],
            crs=7899,
        )
        return origins, stops

    def test_order_independence(self, data):
        """Permuting rows doesn't change scores."""
        origins, stops = data
        params = ScoringParams()

        result1 = compute_coverage_scores(origins, stops, params)
        scores1_dict = dict(zip(range(len(origins)), result1["score"].values))

        # Shuffle origins but keep track of original indices
        shuffle_idx = np.random.RandomState(42).permutation(len(origins))
        origins_shuffled = origins.iloc[shuffle_idx].reset_index(drop=True)
        result2 = compute_coverage_scores(origins_shuffled, stops, params)
        scores2_dict = dict(zip(shuffle_idx, result2["score"].values))

        # Compare scores at same logical positions
        scores1 = np.array([scores1_dict[i] for i in range(len(origins))])
        scores2 = np.array([scores2_dict[i] for i in range(len(origins))])

        np.testing.assert_array_almost_equal(scores1, scores2)


class TestModeWeighting:
    """Test that mode weights affect scores."""

    @pytest.fixture
    def origins(self):
        return gpd.GeoDataFrame(
            {"id": ["O1"]},
            geometry=[Point(0, 0)],
            crs=7899,
        )

    def test_rail_vs_bus_score(self, origins):
        """Rail stops score higher than bus stops at same frequency/distance."""
        rail_stop = gpd.GeoDataFrame(
            {"mode": ["rail"], "frequency": [6.0]},
            geometry=[Point(100, 0)],
            crs=7899,
        )
        bus_stop = gpd.GeoDataFrame(
            {"mode": ["bus"], "frequency": [6.0]},
            geometry=[Point(100, 0)],
            crs=7899,
        )

        params = ScoringParams(w_rail=1.0, w_bus=0.8)
        rail_score = compute_coverage_scores(origins, rail_stop, params).iloc[0][
            "score"
        ]
        bus_score = compute_coverage_scores(origins, bus_stop, params).iloc[0]["score"]

        assert rail_score > bus_score


class TestCatchmentFiltering:
    """Test that stops outside catchment don't contribute."""

    @pytest.fixture
    def params(self):
        return ScoringParams(r_tram=400.0, r_bus=400.0)

    def test_stop_in_catchment(self, params):
        """Stop 400m away (at boundary) contributes."""
        origins = gpd.GeoDataFrame(
            geometry=[Point(0, 0)],
            crs=7899,
        )
        stop = gpd.GeoDataFrame(
            {"mode": ["tram"], "frequency": [6.0]},
            geometry=[Point(400, 0)],
            crs=7899,
        )
        score = compute_coverage_scores(origins, stop, params).iloc[0]["score"]
        assert score > 0

    def test_stop_outside_catchment(self, params):
        """Stop 401m away contributes nothing."""
        origins = gpd.GeoDataFrame(
            geometry=[Point(0, 0)],
            crs=7899,
        )
        stop = gpd.GeoDataFrame(
            {"mode": ["tram"], "frequency": [6.0]},
            geometry=[Point(401, 0)],
            crs=7899,
        )
        score = compute_coverage_scores(origins, stop, params).iloc[0]["score"]
        assert score == 0
