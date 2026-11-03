# transitcov: Pure Accessibility Scoring Library

A deterministic, testable library for computing transit accessibility scores. This is an **installable Python package** with **no database dependencies**.

## Design

- **Pure functions:** All functions are deterministic and testable with synthetic data
- **No database:** Workflows use GeoDataFrames and DataFrames; storage and I/O are caller's responsibility
- **Frozen parameters:** ScoringParams is immutable and hashable, enabling reproducibility and caching
- **Vectorised:** Scores 15,000+ origins in one batch using NumPy

## Install

```bash
cd backend/src/transitcov
pip install -e .
```

Or with test dependencies:

```bash
pip install -e ".[dev]"
```

## Quick Start

```python
import geopandas as gpd
from transitcov.scoring import ScoringParams, compute_coverage_scores

# Load your data (points, not routes)
origins = gpd.read_file("sa1_points.geojson")
stops = gpd.read_file("gtfs_stops.geojson")

# Set parameters (frozen dataclass, included in output for reproducibility)
params = ScoringParams(r_rail=800, r_tram=400, r_bus=400, k=5.0)

# Compute scores
results = compute_coverage_scores(origins, stops, params)

# results has columns:
#   - All origin columns (preserved)
#   - a_i: accessibility index (0 to ~20, depending on k)
#   - score: coverage score (0–100)
#   - n_stops_rail/tram/bus: diagnostic counts
```

## Worked Example (README §4.7)

One tram stop with f=6 departures/hr at the origin, R=400m, w=1.0, k=5.0:

| Distance | Score |
|----------|-------|
| 0 m | 69.9 |
| 200 m | 45.1 |
| 400 m | 25.9 |
| 500 m | 0.0 |

```python
from transitcov.scoring import ScoringParams, compute_coverage_scores
from shapely.geometry import Point
import geopandas as gpd

origins = gpd.GeoDataFrame(
    geometry=[Point(0, 0), Point(200, 0), Point(400, 0), Point(500, 0)],
    crs=7899,
)
stop = gpd.GeoDataFrame(
    {"mode": ["tram"], "frequency": [6.0]},
    geometry=[Point(0, 0)],
    crs=7899,
)
params = ScoringParams(r_tram=400, w_tram=1.0, k=5.0)

result = compute_coverage_scores(origins, stop, params)
print(result["score"])  # [69.9, 45.1, 25.9, 0.0]
```

## Testing

```bash
# All tests (no database required)
pytest tests/

# With coverage
pytest tests/ --cov=src/transitcov --cov-report=html
```

All tests pass deterministically and order-independently; golden files validate the worked example.

## Architecture

```
src/transitcov/
├── __init__.py
├── scoring/
│   ├── __init__.py
│   ├── params.py           # ScoringParams frozen dataclass
│   ├── accessibility.py    # Scoring formula: A_i, score
│   └── equity.py           # Population-weighted statistics (Phase 3)
└── gtfs/
    ├── __init__.py
    ├── modes.py            # route_type → rail|tram|bus mapping
    ├── calendar.py         # service_id → day_type (Phase 2)
    └── service.py          # stop_times → departures/hour (Phase 2)
```

## Parameters (ScoringParams)

All immutable and hashable, included in output rows for reproducibility.

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `r_rail`, `r_tram`, `r_bus` | 800, 400, 400 m | Catchment radius per mode |
| `w_rail`, `w_tram`, `w_bus` | 1.0, 0.8, 0.8 | Mode weight (approximates reliability) |
| `f_cap` | 12/hr | Frequency cap (threshold for mode choice) |
| `k` | 5.0 | Calibration constant (saturation curve) — to be refined post-Phase-2 |
| `window_start_hour`, `window_end_hour` | 7, 9 | Analysis window (07:00–09:00 peak) |

## Formulas (README §4.5)

**Accessibility index** (weighted, distance-decayed service):

$$A_i = \sum_{s \in S_i} w_{m(s)} \cdot \min(f_s, f_{cap}) \cdot e^{-\beta_{m(s)} d_{is}}$$

**Coverage score** (bounded, saturating curve):

$$\text{score}_i = 100 \left(1 - e^{-A_i / k}\right)$$

Where:
- A_i = accessibility at origin i
- S_i = stops within catchment of origin i
- β_m = ln(2) / (R_m / 2) = 2·ln(2) / R_m (distance decay rate)
- d_is = straight-line distance (metres, EPSG:7899)

## Limitations (v1)

- **Distance:** Straight-line only; no network routing (r5py, pgRouting, pandana planned for v2)
- **Frequency:** No temporal variation; one representative weekday per feed
- **Saturation:** Hard cutoff at catchment boundary (smooth kernel planned for v2)
- **Population:** Hex-cell population is area-weighted share of SA1 (approximation; see README §4.8)

## See Also

- [README](../../README.md) — project scope and methodology
- [LOADERS.md](../../docs/LOADERS.md) — data acquisition
- [ISSUES.md](../../ISSUES.md) — known defects and future work (Phase 2, Phase 3, etc.)
