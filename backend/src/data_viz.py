"""
Main script: Load and visualize geospatial data (SA1 boundaries, GTFS stops, census).

Design patterns used:
- Strategy Pattern: Different loaders (GTFSLoader, CensusLoader, SA1Loader)
- Data Classes: Configuration and results are immutable
- Builder Pattern: MapBuilder constructs the visualization step-by-step
- Separation of Concerns: Loaders, transformers, and visualization are independent
"""

import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
from matplotlib import pyplot as plt

# ============================================================================
# CONFIGURATION (Extract all magic numbers)
# ============================================================================

ZONE_MODES = {
    "1": {"name": "Regional Train", "color": "#E74C3C"},
    "2": {"name": "Metropolitan Train", "color": "#3498DB"},
    "3": {"name": "Metropolitan Tram", "color": "#2ECC71"},
    "4": {"name": "Myki Bus", "color": "#F39C12"},
    "5": {"name": "Regional Coach", "color": "#9B59B6"},
    "6": {"name": "Regional Bus", "color": "#E91E63"},
    "10": {"name": "Interstate", "color": "#8B4513"},
    "11": {"name": "SkyBus", "color": "#F1C40F"},
}


@dataclass(frozen=True)
class MapConfig:
    """All visualization parameters"""

    figsize: tuple = (12, 12)
    dpi: int = 300
    background_color: str = "#e0e0e0"
    background_edge_color: str = "#b0b0b0"
    background_edge_width: float = 0.5
    highlight_color: str = "blue"
    highlight_alpha: float = 0.5
    highlight_edge_color: str = "black"
    highlight_edge_width: float = 1.2
    stops_color: str = "red"
    stops_markersize: int = 3
    stops_alpha: float = 0.5
    stops_zorder: int = 3
    title: str = "Victoria SA1 Boundaries with Transit Stops Overlay"
    title_fontsize: int = 16
    title_pad: int = 15
    label_fontsize: int = 8
    label_color: str = "#1a1a1a"
    label_bg_alpha: float = 0.6
    zoom_padding_ratio: float = 0.15
    output_filename: str = "Combined_Victoria_Melbourne_Stops_full.png"


@dataclass(frozen=True)
class DataPaths:
    """All data file paths"""

    gtfs_root: Path
    census_root: Path
    sa1_shapefile: Path

    @staticmethod
    def from_project_root(root: Path) -> "DataPaths":
        """Build paths relative to project root."""
        data_dir = root / "data"
        return DataPaths(
            gtfs_root=data_dir / "_published_public_transport_gtfs_schedule_gtfs",
            census_root=data_dir / "2021_GCP_all_for_VIC_short_header",
            sa1_shapefile=data_dir
            / "SA1_2026_AUST_SHP_GDA2020"
            / "SA1_2026_AUST_GDA2020.shp",
        )


# ============================================================================
# DATA LOADERS (Strategy Pattern)
# ============================================================================


class DataLoader(ABC):
    """Abstract base class for all data loaders."""

    @abstractmethod
    def load(self):
        """Load and return data."""


class GTFSLoader(DataLoader):
    """Load GTFS stops from all zone folders."""

    def __init__(self, gtfs_root: Path):
        self.gtfs_root = gtfs_root

    def load(self) -> pd.DataFrame:
        """Load stops.txt from all GTFS zones and combine."""
        all_stops = []

        for zone_dir in sorted(self.gtfs_root.iterdir()):
            if not zone_dir.is_dir():
                continue

            stops_path = zone_dir / "google_transit" / "stops.txt"
            if not stops_path.exists():
                continue

            try:
                zone_stops = pd.read_csv(stops_path)
                zone_stops["zone"] = zone_dir.name
                if zone_dir.name in ZONE_MODES:
                    zone_stops["mode"] = ZONE_MODES[zone_dir.name]["name"]
                    zone_stops["mode_color"] = ZONE_MODES[zone_dir.name]["color"]
                all_stops.append(zone_stops)
                print(f"Zone {zone_dir.name}: {len(zone_stops)} stops")
            except (pd.errors.ParserError, OSError) as e:
                print(f"Error reading {zone_dir.name}: {e}")

        if not all_stops:
            raise ValueError("No stops found in any zone")

        combined = pd.concat(all_stops, ignore_index=True)
        print(f"\nTotal stops across all zones: {len(combined)}\n")
        return combined


class SA1Loader(DataLoader):
    """Load SA1 boundaries from shapefile."""

    def __init__(self, shapefile_path: Path):
        self.shapefile_path = shapefile_path

    def load(self) -> gpd.GeoDataFrame:
        """Load shapefile and filter to Victoria."""
        gdf = gpd.read_file(self.shapefile_path)
        vic_only = gdf[gdf["SA1_CODE26"].astype(str).str.startswith("2")].copy()
        print(f"Loaded {len(vic_only)} Victoria SA1 boundaries\n")
        return vic_only


class CensusLoader(DataLoader):
    """Load 2021 Census population data."""

    def __init__(self, census_root: Path):
        self.census_root = census_root
        self.g01_path = (
            census_root
            / "2021 Census GCP All Geographies for VIC"
            / "SA1"
            / "VIC"
            / "2021Census_G01_VIC_SA1.csv"
        )

    def load(self) -> pd.DataFrame:
        """Load G01 table (population)."""
        if not self.g01_path.exists():
            raise FileNotFoundError(f"Census file not found: {self.g01_path}")

        df = pd.read_csv(self.g01_path)
        print(f"Loaded {len(df)} Census records\n")
        return df


# ============================================================================
# MAP BUILDER (Builder Pattern)
# ============================================================================


class MapBuilder:
    """Construct a visualization layer-by-layer."""

    def __init__(self, config: MapConfig):
        self.config = config
        self.fig, self.ax = plt.subplots(figsize=config.figsize)

    def add_background_layer(self, gdf: gpd.GeoDataFrame) -> "MapBuilder":
        """Add the full-state background layer."""
        gdf.plot(
            ax=self.ax,
            color=self.config.background_color,
            edgecolor=self.config.background_edge_color,
            linewidth=self.config.background_edge_width,
        )
        return self

    def add_highlight_layer(self, gdf: gpd.GeoDataFrame) -> "MapBuilder":
        """Add the highlighted region (e.g., Melbourne CBD) layer."""
        gdf.plot(
            ax=self.ax,
            color=self.config.highlight_color,
            alpha=self.config.highlight_alpha,
            edgecolor=self.config.highlight_edge_color,
            linewidth=self.config.highlight_edge_width,
        )
        return self

    def add_stops_layer(self, stops_gdf: gpd.GeoDataFrame) -> "MapBuilder":
        """Add the transit stops (points) layer, colored by transport mode."""
        if "mode_color" in stops_gdf.columns:
            for mode in stops_gdf["mode"].unique():
                mode_stops = stops_gdf[stops_gdf["mode"] == mode]
                color = mode_stops["mode_color"].iloc[0]
                mode_stops.plot(
                    ax=self.ax,
                    color=color,
                    markersize=self.config.stops_markersize,
                    zorder=self.config.stops_zorder,
                    alpha=self.config.stops_alpha,
                    label=mode,
                )
            self.ax.legend(
                loc="upper left", fontsize=self.config.label_fontsize, framealpha=0.9
            )
        else:
            stops_gdf.plot(
                ax=self.ax,
                color=self.config.stops_color,
                markersize=self.config.stops_markersize,
                zorder=self.config.stops_zorder,
                alpha=self.config.stops_alpha,
            )
        return self

    def add_labels(self, gdf: gpd.GeoDataFrame, label_column: str) -> "MapBuilder":
        """Add text labels at centroid of each region."""
        dissolved = gdf.dissolve(by=label_column).reset_index()

        for _, row in dissolved.iterrows():
            centroid = row["geometry"].centroid
            display_name = row[label_column].replace(" - ", "\n")

            self.ax.text(
                x=centroid.x,
                y=centroid.y,
                s=display_name,
                fontsize=self.config.label_fontsize,
                fontweight="bold",
                color=self.config.label_color,
                ha="center",
                va="center",
                zorder=4,
                bbox={
                    "boxstyle": "round,pad=0.2",
                    "fc": "white",
                    "alpha": self.config.label_bg_alpha,
                    "ec": "none",
                },
            )
        return self

    def add_title(self) -> "MapBuilder":
        """Add map title."""
        self.ax.set_title(
            self.config.title,
            fontsize=self.config.title_fontsize,
            pad=self.config.title_pad,
        )
        self.ax.axis("off")
        return self

    def zoom_to_bounds(self, gdf: gpd.GeoDataFrame) -> "MapBuilder":
        """Zoom axes to a GeoDataFrame's bounds with padding."""
        minx, miny, maxx, maxy = gdf.total_bounds
        pad_x = (maxx - minx) * self.config.zoom_padding_ratio
        pad_y = (maxy - miny) * self.config.zoom_padding_ratio

        self.ax.set_xlim(minx - pad_x, maxx + pad_x)
        self.ax.set_ylim(miny - pad_y, maxy + pad_y)
        return self

    def save(self, filepath: Path) -> "MapBuilder":
        """Save the figure to disk."""
        plt.savefig(str(filepath), dpi=self.config.dpi, bbox_inches="tight")
        print(f"Saved to {filepath}")
        return self

    def show(self) -> "MapBuilder":
        """Display the figure."""
        plt.show()
        return self

    def close(self) -> None:
        """Clean up the figure."""
        plt.close(self.fig)


# ============================================================================
# ORCHESTRATION
# ============================================================================


def setup_extraction(gtfs_root: Path) -> None:
    """Extract all GTFS ZIP files if not already done."""
    for level_dir in gtfs_root.iterdir():
        if not level_dir.is_dir():
            continue
        for zip_path in level_dir.iterdir():
            if not zip_path.is_file() or zip_path.suffix.lower() != ".zip":
                continue

            extract_dir = level_dir / zip_path.stem
            if extract_dir.is_dir():
                print(f"Already extracted: {zip_path}")
                continue

            extract_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path) as zip_ref:
                zip_ref.extractall(extract_dir)
            print(f"Extracted: {zip_path} -> {extract_dir}")


def main():
    """Main orchestration: load data, build visualization."""
    # Setup
    root = Path(__file__).resolve().parent.parent.parent
    paths = DataPaths.from_project_root(root)
    config = MapConfig()

    # Extract GTFS data
    print("=" * 80)
    print("EXTRACTING GTFS DATA")
    print("=" * 80)
    setup_extraction(paths.gtfs_root)

    # Load data
    print("=" * 80)
    print("LOADING DATA")
    print("=" * 80)

    stops_df = GTFSLoader(paths.gtfs_root).load()
    sa1_gdf = SA1Loader(paths.sa1_shapefile).load()

    # Transform stops to GeoDataFrame with proper CRS
    stops_gdf = gpd.GeoDataFrame(
        stops_df,
        geometry=gpd.points_from_xy(stops_df["stop_lon"], stops_df["stop_lat"]),
        crs=4326,
    ).to_crs(sa1_gdf.crs)

    # Filter to Melbourne CBD region
    CBD_SA2_NAMES = [
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
    ]
    melbourne_sa2 = sa1_gdf[sa1_gdf["SA2_NAME26"].isin(CBD_SA2_NAMES)]

    print("=" * 80)
    print("BUILDING VISUALIZATION")
    print("=" * 80)

    (
        MapBuilder(config)
        .add_background_layer(sa1_gdf)
        .add_highlight_layer(melbourne_sa2)
        .add_stops_layer(stops_gdf)
        # .add_labels(melbourne_sa2, "SA2_NAME26") # uncomment to see the areas
        .add_title()
        .zoom_to_bounds(melbourne_sa2)
        .save(root / config.output_filename)
        .close()
    )


if __name__ == "__main__":
    main()
