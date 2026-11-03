"""transitcov: Pure-function library for transit accessibility scoring.

This library provides deterministic, testable functions for computing
accessibility scores. It has no database dependencies; all data flows
through GeoDataFrames and DataFrames.

The library computes coverage scores following README §4.5: a place-based
cumulative-opportunity measure that discounts service by distance and
combines it across modes.
"""

__version__ = "0.1.0"
