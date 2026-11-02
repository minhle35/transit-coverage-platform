"""The study area, defined once.

Scope is **not** a load-time concern. README 7.4 defines `core` as "versioned,
conformed entities" -- the feed as received, conformed -- so filtering a study
area during load makes `core.stop` a partial record of the feed. That is what
produced the orphan rows in ISSUES.md I-09: the loaders upsert and never
delete, so narrowing the scope left 571 out-of-scope stops behind with no
version boundary to filter them out by.

It was also numerically wrong. A stop just outside the boundary still serves
residents inside it when they are within its catchment radius, so filtering
stops by study area truncates every boundary SA1's service.

So `core` holds everything the feed publishes, and scope is applied where
results are computed -- in `marts`, which README 7.4 already designates for
published results.
"""

from __future__ import annotations

# The project study area (README 1.3, 1.4: "the study area is Greater
# Melbourne"). ABS GCCSA code, carried on core.area_sa1.gcc_code.
# 11,487 SA1s, 4,917,633 people in the 2021 Census.
GREATER_MELBOURNE_GCC = "2GMEL"

# A development subset: the eleven inner SA2s, 237 SA1s and 100,256 people, or
# about 2% of Greater Melbourne. Useful for fast iteration and for the
# visualisation in scripts/data_viz.py. Never a load filter -- see the module
# docstring.
MELBOURNE_CBD_SA2_NAMES = (
    "Melbourne CBD - East",
    "Melbourne CBD - North",
    "Melbourne CBD - West",
    "East Melbourne",
    "Melbourne Airport",
    "North Melbourne",
    "Port Melbourne",
    "Port Melbourne Industrial",
    "South Melbourne",
    "West Melbourne - Industrial",
    "West Melbourne - Residential",
)
