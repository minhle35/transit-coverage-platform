"""Tests for GTFS route_type to mode mapping."""

import pytest

from transitcov.gtfs.modes import gtfs_route_type_to_mode


class TestModeMapping:
    """Test GTFS route_type to canonical mode mapping."""

    def test_tram_modes(self):
        """Route types 0, 6 map to tram."""
        assert gtfs_route_type_to_mode(0) == "tram"
        assert gtfs_route_type_to_mode(6) == "tram"

    def test_rail_modes(self):
        """Route types 2, 100, 102, 103, 104, 400, 401 map to rail."""
        rail_types = [2, 100, 102, 103, 104, 400, 401]
        for rt in rail_types:
            assert gtfs_route_type_to_mode(rt) == "rail"

    def test_bus_modes(self):
        """Route types 1, 3, 11, 12, 7xx map to bus."""
        bus_types = [1, 3, 11, 12, 204, 207, 700, 701, 704, 705, 706, 707, 708, 709, 710, 711, 712, 713, 714, 715, 716, 717, 718, 719]
        for rt in bus_types:
            assert gtfs_route_type_to_mode(rt) == "bus"

    def test_other_grade_separated(self):
        """Route types 5, 7, 9 (funicular, cable, etc.) map to rail."""
        grade_sep = [5, 7, 9]
        for rt in grade_sep:
            assert gtfs_route_type_to_mode(rt) == "rail"

    def test_water_transport(self):
        """Route types 4, 10 (water transport) map to rail."""
        assert gtfs_route_type_to_mode(4) == "rail"
        assert gtfs_route_type_to_mode(10) == "rail"

    def test_string_input(self):
        """Route type can be provided as string."""
        assert gtfs_route_type_to_mode("0") == "tram"
        assert gtfs_route_type_to_mode("2") == "rail"
        assert gtfs_route_type_to_mode("3") == "bus"

    def test_invalid_route_type(self):
        """Invalid route type raises ValueError."""
        with pytest.raises(ValueError):
            gtfs_route_type_to_mode(999)
