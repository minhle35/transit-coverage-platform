"""Accessibility scoring formula: A_i and score functions.

Pure functions for computing coverage scores. README §4.5 has the formulas.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from transitcov.scoring.params import ScoringParams

if TYPE_CHECKING:
    import geopandas as gpd


def decay_rate_for_mode(mode: str, params: ScoringParams) -> float:
    """Distance decay rate (β_m) for a mode.

    The decay curve is exponential: a stop at half the catchment radius
    carries half the weight of one at the origin, and one at the boundary
    carries 1/4. β_m = ln(2) / (R_m / 2) = 2·ln(2) / R_m.

    Args:
        mode: One of 'rail', 'tram', 'bus'
        params: ScoringParams with catchment radii

    Returns:
        Decay rate in m⁻¹
    """
    r_m = params.catchment_for_mode(mode)
    return 2.0 * math.log(2) / r_m


def compute_accessibility(
    origin_distances: dict[str, np.ndarray],
    stop_frequencies: dict[str, np.ndarray],
    stop_modes: np.ndarray,
    params: ScoringParams,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Compute accessibility index A_i for each origin.

    Vectorised over all origins and stops in one batch. For each origin:
    - Find all stops within catchment (d_is ≤ R_m)
    - Apply distance decay and mode weight
    - Sum contributions across modes

    Formula (README §4.5):
        A_i = Σ w_m · min(f_s, f_cap) · exp(-β_m · d_is)

    Args:
        origin_distances: Dict {mode: array of shape (n_origins, n_stops)}
            Distances in metres from each origin to each stop, by mode.
            NaN for stops outside catchment.
        stop_frequencies: Dict {mode: array of shape (n_stops,)}
            Departures per hour for each stop, by mode.
        stop_modes: Array of shape (n_stops,) with mode labels.
        params: ScoringParams

    Returns:
        (a_i, intermediate_values) where:
        - a_i: Array of shape (n_origins,) with A_i for each origin
        - intermediate_values: Dict of intermediate results for diagnostics
    """
    modes = ["rail", "tram", "bus"]
    n_origins = origin_distances[modes[0]].shape[0]
    a_i = np.zeros(n_origins)

    intermediate = {mode: np.zeros((n_origins,)) for mode in modes}

    for mode in modes:
        distances = origin_distances[mode]  # (n_origins, n_stops)
        frequencies = stop_frequencies[mode]  # (n_stops,)

        # Catchment and frequency cap
        catchment = params.catchment_for_mode(mode)
        capped_freq = np.minimum(frequencies, params.f_cap)

        # Distance decay: β_m = 2·ln(2) / R_m
        beta_m = decay_rate_for_mode(mode, params)

        # Weight by mode
        w_m = params.weight_for_mode(mode)

        # For each origin, sum contributions from stops in catchment
        # d_is ≤ catchment → include; else → exclude (set to 0)
        in_catchment = distances <= catchment  # (n_origins, n_stops)
        distances_in_catchment = distances.copy()
        distances_in_catchment[~in_catchment] = catchment + 1  # Ensure exp(-β·d) ≈ 0

        # Contribution per stop: w_m · freq · exp(-β · d)
        contributions = w_m * capped_freq * np.exp(-beta_m * distances_in_catchment)
        # Zero out stops outside catchment
        contributions[~in_catchment] = 0

        # Sum across stops for each origin
        mode_contribution = contributions.sum(axis=1)
        a_i += mode_contribution
        intermediate[mode] = mode_contribution

    return a_i, intermediate


def score_from_accessibility(a_i: np.ndarray, params: ScoringParams) -> np.ndarray:
    """Convert accessibility index A_i to bounded score in [0, 100).

    Formula (README §4.5):
        score_i = 100 · (1 - exp(-A_i / k))

    The outer curve is strictly increasing and saturating: the first
    services move the score quickly, later ones add less, and the result
    never exceeds 100.

    Args:
        a_i: Array of shape (n_origins,) with accessibility index
        params: ScoringParams with calibration constant k

    Returns:
        Array of shape (n_origins,) with scores in [0, 100)
    """
    scores = 100.0 * (1.0 - np.exp(-a_i / params.k))
    return np.clip(scores, 0.0, 100.0)


def compute_coverage_scores(
    origins: gpd.GeoDataFrame,
    stops: gpd.GeoDataFrame,
    params: ScoringParams,
) -> pd.DataFrame:
    """Compute coverage scores for origins from a set of stops.

    Main entry point. Pure function: given origins, stops, and parameters,
    returns a deterministic result. Order of inputs doesn't matter (results
    are order-independent thanks to vectorisation).

    Args:
        origins: GeoDataFrame with:
            - geometry: Point geometries (EPSG:7899 metric)
            - Any other columns preserved in output
        stops: GeoDataFrame with:
            - geometry: Point geometries (EPSG:7899 metric)
            - mode: String column (rail/tram/bus)
            - frequency: Float column (departures per hour)
        params: ScoringParams

    Returns:
        DataFrame with one row per origin, containing:
        - All origin columns
        - a_i: Accessibility index (intermediate)
        - score: Coverage score in [0, 100)
        - n_stops_rail/tram/bus: Count of stops used per mode
    """
    if len(origins) == 0:
        return pd.DataFrame()

    n_origins = len(origins)
    n_stops = len(stops)

    # Compute distances from each origin to each stop
    # Shape: (n_origins, n_stops), values in metres
    distances_matrix = origins.geometry.apply(
        lambda o: stops.geometry.distance(o).values
    )
    distances_matrix = np.array(distances_matrix.tolist())

    # Group by mode
    origin_distances = {}
    stop_frequencies = {}
    for mode in ["rail", "tram", "bus"]:
        mode_stops = stops[stops["mode"] == mode]
        if len(mode_stops) > 0:
            # Only compute distances to stops of this mode
            mode_indices = mode_stops.index
            origin_distances[mode] = distances_matrix[:, mode_stops.index]
            stop_frequencies[mode] = mode_stops["frequency"].values
        else:
            # No stops of this mode
            origin_distances[mode] = np.full((n_origins, 0), np.nan)
            stop_frequencies[mode] = np.array([])

    # Compute accessibility and scores
    a_i, intermediate = compute_accessibility(
        origin_distances, stop_frequencies, stops["mode"].values, params
    )
    scores = score_from_accessibility(a_i, params)

    # Build result DataFrame
    result = origins.copy()
    result["a_i"] = a_i
    result["score"] = scores

    # Count stops per mode (for diagnostics)
    for mode in ["rail", "tram", "bus"]:
        result[f"n_stops_{mode}"] = (stops["mode"] == mode).sum()

    return result
