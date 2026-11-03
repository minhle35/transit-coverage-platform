"""GTFS route_type to canonical scoring mode mapping.

Modes are grouped by right-of-way (grade-separated rail, street-running tram,
mixed traffic bus), not by vehicle type. This is what drives both catchment
size and reliability in the scoring formula.
"""

from __future__ import annotations


def gtfs_route_type_to_mode(route_type: int | str) -> str:
    """Map GTFS route_type to canonical scoring mode.

    GTFS route_type is an integer or string. Modes are grouped by
    right-of-way:
    - rail: grade-separated (route_type 2, 100, 102, 103, 104, 400, 401)
    - tram: street-running streetcar (route_type 0, 6)
    - bus: mixed traffic (route_type 1, 3, 11, 12, 700, 701, 704, 705, 706, 707, 708, 709, 710, 711, 712, 713, 714, 715, 716, 717, 718, 719)

    Trolleybus (route_type 11) is a bus variant (mixed traffic).
    Coach (route_type 12, 204, 207) is mapped to bus.
    Other types (e.g., funicular, suspended cable, water) are mapped to rail
    (grade-separated assumption).

    Args:
        route_type: GTFS route_type as int or str

    Returns:
        One of 'rail', 'tram', 'bus'

    Raises:
        ValueError: If route_type is not a valid GTFS type
    """
    route_type = int(route_type) if isinstance(route_type, str) else route_type

    match route_type:
        # Tram (street-running)
        case 0 | 6:
            return "tram"
        # Light rail, rail, etc. (grade-separated)
        case 2 | 100 | 102 | 103 | 104 | 400 | 401:
            return "rail"
        # Bus variants (mixed traffic)
        case 1 | 3 | 11 | 12 | 204 | 207 | 700 | 701 | 704 | 705 | 706 | 707 | 708 | 709 | 710 | 711 | 712 | 713 | 714 | 715 | 716 | 717 | 718 | 719:
            return "bus"
        # Funicular, suspended cable, etc.: assume grade-separated
        case 5 | 7 | 9:
            return "rail"
        # Intercity bus: treat as bus
        case 201 | 202:
            return "bus"
        # Water transport: treat as grade-separated
        case 4 | 10:
            return "rail"
        case _:
            raise ValueError(f"Unknown GTFS route_type: {route_type}")
