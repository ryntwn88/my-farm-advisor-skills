#!/usr/bin/env python3
"""
eda_field_portfolio_weather.py — Weather module

Part of the Assignment 2 "Operational Stability and Risk" EDA subskill.
Analyzes environmental volatility across the three-grower portfolio.

Outputs (static PNG/CSV, no interactive dashboard):
  1. weather_spring_precip_variance_timeseries.png — Apr+May precip per year for one NE field
  2. weather_monthly_temp_heatmap.png          — avg monthly temp across 3 growers
  3. weather_ne_gdd_comparison.csv            — cumulative GDD per Nebraska field (2025)
  4. weather_precip_map.png                  — boundaries colored by 2025 total precip

Usage:
    python scripts/eda/eda_field_portfolio_weather.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

matplotlib.use("Agg")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
RUNTIME_ROOT = Path("/home/coder/my-farm-advisor-runtime/data-pipeline")
GROWERS_DIR = RUNTIME_ROOT / "growers"
OUTPUT_DIR = RUNTIME_ROOT / "eda" / "field-portfolio" / "weather"

GROWERS = {
    "il-grower": {
        "label": "Illinois",
        "boundary": GROWERS_DIR
        / "il-grower"
        / "farms"
        / "il-grower-illinois"
        / "boundary"
        / "field_boundaries.geojson",
        "weather": GROWERS_DIR
        / "il-grower"
        / "farms"
        / "il-grower-illinois"
        / "derived"
        / "tables"
        / "il_grower_illinois_weather_2021_2025.csv",
    },
    "ia-grower": {
        "label": "Iowa",
        "boundary": GROWERS_DIR
        / "ia-grower"
        / "farms"
        / "ia-grower-iowa"
        / "boundary"
        / "field_boundaries.geojson",
        "weather": GROWERS_DIR
        / "ia-grower"
        / "farms"
        / "ia-grower-iowa"
        / "derived"
        / "tables"
        / "ia_grower_iowa_weather_2021_2025.csv",
    },
    "ne-grower": {
        "label": "Nebraska",
        "boundary": GROWERS_DIR
        / "ne-grower"
        / "farms"
        / "ne-grower-nebraska"
        / "boundary"
        / "field_boundaries.geojson",
        "weather": GROWERS_DIR
        / "ne-grower"
        / "farms"
        / "ne-grower-nebraska"
        / "derived"
        / "tables"
        / "ne_grower_nebraska_weather_2021_2025.csv",
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_weather(grower_slug: str) -> pd.DataFrame:
    """Load weather CSV for a grower, parse dates."""
    path = GROWERS[grower_slug]["weather"]
    df = pd.read_csv(path, parse_dates=["date"])
    df["grower"] = GROWERS[grower_slug]["label"]
    df["grower_slug"] = grower_slug
    return df


def load_boundaries(grower_slug: str) -> gpd.GeoDataFrame:
    """Load boundary GeoJSON for a grower."""
    return gpd.read_file(GROWERS[grower_slug]["boundary"])


# ---------------------------------------------------------------------------
# 1. Spring precipitation variance time-series (single Nebraska field)
# ---------------------------------------------------------------------------

def plot_spring_precip_variance() -> Path:
    """Plot Apr+May total precipitation for one representative field per grower, 2021-2025."""
    plt.figure(figsize=(11, 6))
    sns.set_style("whitegrid")

    palette = {"Illinois": "#2E86AB", "Iowa": "#A23B72", "Nebraska": "#F18F01"}
    order = [("il-grower", "Illinois"), ("ia-grower", "Iowa"), ("ne-grower", "Nebraska")]

    all_yearly: list[pd.DataFrame] = []

    for slug, label in order:
        df = load_weather(slug)

        # Pick first field as representative (all have same record count)
        rep_field = df["field_id"].iloc[0]

        subset = df[df["field_id"] == rep_field].copy()
        subset["year"] = subset["date"].dt.year
        subset["month"] = subset["date"].dt.month

        spring = subset[subset["month"].isin([4, 5])].copy()
        yearly = spring.groupby("year")["PRECTOTCORR"].sum().reset_index()
        yearly.columns = ["year", "spring_precip_mm"]
        yearly["grower"] = label
        yearly["field_id"] = rep_field
        all_yearly.append(yearly)

        plt.plot(
            yearly["year"],
            yearly["spring_precip_mm"],
            marker="o",
            markersize=7,
            linewidth=2.2,
            color=palette[label],
            label=f"{label} ({rep_field[-8:]})",
        )

    combined = pd.concat(all_yearly, ignore_index=True)
    max_val = combined["spring_precip_mm"].max()

    plt.title(
        "Spring (Apr-May) Precipitation Variance\n"
        "One Representative Field per Grower (2021–2025)",
        fontsize=14,
        fontweight="bold",
    )
    plt.xlabel("Year", fontsize=12)
    plt.ylabel("Total Precipitation (mm)", fontsize=12)
    plt.xticks(sorted(combined["year"].unique()))
    plt.ylim(0, max_val * 1.2)
    plt.legend(loc="upper left", title="Grower")
    plt.tight_layout()

    out_path = OUTPUT_DIR / "weather_spring_precip_variance_timeseries.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out_path.name}")
    return out_path


# ---------------------------------------------------------------------------
# 2. Monthly temperature heatmap across 3 growers
# ---------------------------------------------------------------------------

def plot_monthly_temp_heatmap() -> Path:
    """Heatmap of average monthly T2M across the three growers."""
    frames = [load_weather(slug) for slug in GROWERS]
    df = pd.concat(frames, ignore_index=True)

    df["month"] = df["date"].dt.month
    df["month_name"] = df["date"].dt.month_name()

    # Average across all fields within each grower per month
    monthly = df.groupby(["grower", "month"])["T2M"].mean().reset_index()

    # Pivot: growers as rows, months as columns
    pivot = monthly.pivot(index="grower", columns="month", values="T2M")
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    pivot.columns = month_labels
    pivot = pivot.reindex(["Illinois", "Iowa", "Nebraska"])

    plt.figure(figsize=(12, 5))
    sns.set_style("white")

    ax = sns.heatmap(
        pivot,
        annot=True,
        fmt=".1f",
        cmap="RdYlBu_r",
        center=15,
        linewidths=0.5,
        cbar_kws={"label": "Avg Temperature (°C)"},
    )

    ax.set_title(
        "Average Monthly Temperature by Grower\n"
        "(Environmental Heat Profile — Risk of Heat Stress)",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )
    ax.set_xlabel("Month", fontsize=12)
    ax.set_ylabel("Grower", fontsize=12)

    plt.tight_layout()
    out_path = OUTPUT_DIR / "weather_monthly_temp_heatmap.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out_path.name}")
    return out_path


# ---------------------------------------------------------------------------
# 3. GDD comparison across Nebraska fields (2025)
# ---------------------------------------------------------------------------

def compute_ne_gdd_comparison() -> Path:
    """Calculate cumulative GDD (base 10°C) per Nebraska field for 2025."""
    df = load_weather("ne-grower")
    df["year"] = df["date"].dt.year

    df_2025 = df[df["year"] == 2025].copy()

    # Standard GDD: max(0, (TMAX + TMIN)/2 - base)
    df_2025["daily_mean_temp"] = (df_2025["T2M_MAX"] + df_2025["T2M_MIN"]) / 2.0
    df_2025["gdd"] = np.maximum(0, df_2025["daily_mean_temp"] - 10.0)

    gdd_by_field = df_2025.groupby("field_id")["gdd"].sum().reset_index()
    gdd_by_field.columns = ["field_id", "cumulative_gdd_2025"]
    gdd_by_field["cumulative_gdd_2025"] = gdd_by_field["cumulative_gdd_2025"].round(1)

    # Sort descending
    gdd_by_field = gdd_by_field.sort_values("cumulative_gdd_2025", ascending=False).reset_index(drop=True)

    # Add rank and grower
    gdd_by_field["rank"] = range(1, len(gdd_by_field) + 1)
    gdd_by_field["grower"] = "Nebraska"

    out_path = OUTPUT_DIR / "weather_ne_gdd_comparison.csv"
    gdd_by_field.to_csv(out_path, index=False)
    print(f"  ✓ {out_path.name}")
    return out_path


# ---------------------------------------------------------------------------
# 4. Geospatial map — boundaries colored by 2025 cumulative precipitation
# ---------------------------------------------------------------------------

def plot_precip_map() -> Path:
    """Map field boundaries colored by total 2025 precipitation."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 7))

    order = [
        ("Illinois", "il-grower"),
        ("Iowa", "ia-grower"),
        ("Nebraska", "ne-grower"),
    ]

    # Load all weather and compute 2025 total precip per field
    all_precip: dict[str, float] = {}
    for slug in GROWERS:
        df = load_weather(slug)
        df["year"] = df["date"].dt.year
        precip_2025 = df[df["year"] == 2025].groupby("field_id")["PRECTOTCORR"].sum()
        all_precip.update(precip_2025.to_dict())

    # Global vmin/vmax for consistent coloring
    precip_values = np.array(list(all_precip.values()))
    vmin = float(np.percentile(precip_values, 5))
    vmax = float(np.percentile(precip_values, 95))

    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    cmap = matplotlib.colormaps.get_cmap("YlGnBu")

    for ax, (grower_label, slug) in zip(axes, order):
        gdf = load_boundaries(slug).to_crs(epsg=4326)
        gdf["total_precip_2025"] = gdf["field_id"].map(all_precip)

        facecolors = cmap(norm(gdf["total_precip_2025"].values))

        gdf.plot(
            color=facecolors,
            linewidth=0.8,
            edgecolor="black",
            alpha=0.9,
            ax=ax,
        )

        # Tight crop
        bounds = gdf.total_bounds
        margin_x = (bounds[2] - bounds[0]) * 0.15
        margin_y = (bounds[3] - bounds[1]) * 0.15
        ax.set_xlim(bounds[0] - margin_x, bounds[2] + margin_x)
        ax.set_ylim(bounds[1] - margin_y, bounds[3] + margin_y)

        ax.set_title(f"{grower_label}", fontsize=12, fontweight="bold")
        ax.set_xlabel("Longitude", fontsize=9)
        ax.set_ylabel("Latitude", fontsize=9)
        ax.set_aspect("equal")

    # Shared vertical colorbar on the right
    fig.subplots_adjust(right=0.88)
    cbar_ax = fig.add_axes([0.91, 0.15, 0.025, 0.7])
    sm = matplotlib.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, cax=cbar_ax)
    cbar.set_label("2025 Total Precipitation (mm)", fontsize=11)

    fig.suptitle(
        "Field Boundaries Colored by 2025 Cumulative Precipitation\n"
        "(Darker Blue = Wetter / Higher Moisture Risk)",
        fontsize=14,
        fontweight="bold",
        y=1.02,
    )

    out_path = OUTPUT_DIR / "weather_precip_map.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out_path.name}")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("Weather Module — Operational Stability & Risk")
    print("=" * 60)

    _ensure_output_dir()

    print("\n[1/4] Spring precipitation variance time-series...")
    plot_spring_precip_variance()

    print("\n[2/4] Monthly temperature heatmap...")
    plot_monthly_temp_heatmap()

    print("\n[3/4] Nebraska GDD comparison...")
    compute_ne_gdd_comparison()

    print("\n[4/4] Precipitation geospatial map...")
    plot_precip_map()

    print(f"\n{'=' * 60}")
    print(f"All outputs saved to: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
