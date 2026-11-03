"""Frozen parameters for the accessibility scoring function.

These are the explicit assumptions that calibrate the model. They are frozen
(immutable) so they can be hashed and stored with results for reproducibility.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringParams:
    """Accessibility scoring parameters.

    All parameters are immutable and hashable so they can be stored with
    results and used as a cache key. See README §4.6 for the reasoning.
    """

    # Catchment radii (metres)
    r_rail: float = 800.0  # Common planning rule for rail access
    r_tram: float = 400.0  # Common planning rule for street-level access
    r_bus: float = 400.0   # Common planning rule for street-level access

    # Mode weights (dimensionless; approximate reliability penalty)
    w_rail: float = 1.0    # Reference (least traffic-exposed)
    w_tram: float = 0.8    # Penalises traffic exposure vs. rail
    w_bus: float = 0.8     # Penalises traffic exposure vs. rail

    # Frequency cap (departures per hour)
    f_cap: float = 12.0    # Threshold where passengers switch to timetable planning

    # Calibration constant (dimensionless; sets saturation curve)
    # To be calibrated from observed A_i distribution targeting 95th percentile ≈ 90
    k: float = 5.0         # Placeholder; calibrated after core.stop_service_hourly populated

    # Analysis window (hour as 0–23)
    window_start_hour: int = 7
    window_end_hour: int = 9

    def __post_init__(self) -> None:
        """Validate parameter ranges."""
        if self.r_rail <= 0 or self.r_tram <= 0 or self.r_bus <= 0:
            raise ValueError("Catchment radii must be positive")
        if self.w_rail <= 0 or self.w_tram <= 0 or self.w_bus <= 0:
            raise ValueError("Mode weights must be positive")
        if self.f_cap <= 0:
            raise ValueError("Frequency cap must be positive")
        if self.k <= 0:
            raise ValueError("Calibration constant k must be positive")
        if not (0 <= self.window_start_hour < 24):
            raise ValueError("window_start_hour must be 0–23")
        if not (0 <= self.window_end_hour < 24):
            raise ValueError("window_end_hour must be 0–23")
        if self.window_start_hour >= self.window_end_hour:
            raise ValueError("window_start_hour must be < window_end_hour")

    def catchment_for_mode(self, mode: str) -> float:
        """Return catchment radius (metres) for a mode.

        Args:
            mode: One of 'rail', 'tram', 'bus'

        Returns:
            Catchment radius in metres

        Raises:
            ValueError: If mode is unknown
        """
        match mode:
            case "rail":
                return self.r_rail
            case "tram":
                return self.r_tram
            case "bus":
                return self.r_bus
            case _:
                raise ValueError(f"Unknown mode: {mode}")

    def weight_for_mode(self, mode: str) -> float:
        """Return mode weight (dimensionless) for a mode.

        Args:
            mode: One of 'rail', 'tram', 'bus'

        Returns:
            Mode weight

        Raises:
            ValueError: If mode is unknown
        """
        match mode:
            case "rail":
                return self.w_rail
            case "tram":
                return self.w_tram
            case "bus":
                return self.w_bus
            case _:
                raise ValueError(f"Unknown mode: {mode}")
