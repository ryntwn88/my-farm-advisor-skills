#!/usr/bin/env python3
"""
eda_field_portfolio_cdl.py — CDL / Cropland Data Layer module

Part of the Assignment 2 "Operational Stability and Risk" EDA subskill.
Analyzes strategic planting decisions across the three-grower portfolio.

Outputs (static PNG/CSV, no interactive dashboard):
  1. cdl_diversity_score_line.png      — Shannon diversity per grower over time
  2. cdl_rotation_frequency.png         — rotation pattern frequencies
  3. cdl_iowa_transition_matrix.csv  — crop transition probabilities (Iowa)
  4. cdl_dominant_crop_map.png         — boundaries colored by 2025 dominant crop

Usage:
    python scripts/eda/eda_field_portfolio_cdl.py
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
OUTPUT_DIR = RUNTIME_ROOT / "eda" / "field-portfolio" / "cdl"

GROWERS = {
    "il-grower": {
        "label": "Illinois",
        "boundary": GROWERS_DIR
        / "il-grower"
        / "farms"
        / "il-grower-illinois"
        / "boundary"
        / "field_boundaries.geojson",
        "cdl": GROWERS_DIR
        / "il-grower"
        / "farms"
        / "il-grower-illinois"
        / "derived"
        / "tables"
        / "il_grower_illinois_cdl_2021_2025_full_composition.csv",
    },
    "ia-grower": {
        "label": "Iowa",
        "boundary": GROWERS_DIR
        / "ia-grower"
        / "farms"
        / "ia-grower-iowa"
        / "boundary"
        / "field_boundaries.geojson",
        "cdl": GROWERS_DIR
        / "ia-grower"
        / "farms"
        / "ia-grower-iowa"
        / "derived"
        / "tables"
        / "ia_grower_iowa_cdl_2021_2025_full_composition.csv",
    },
    "ne-grower": {
        "label": "Nebraska",
        "boundary": GROWERS_DIR
        / "ne-grower"
        / "farms"
        / "ne-grower-nebraska"
        / "boundary"
        / "field_boundaries.geojson",
        "cdl": GROWERS_DIR
        / "ne-grower"
        / "farms"
        / "ne-grower-nebraska"
        / "derived"
        / "tables"
        / "ne_grower_nebraska_cdl_2021_2025_full_composition.csv",
    },
}

# Crop colors for consistent visualization across artifacts
CROP_COLORS = {
    "Corn": "#F4D03F",
    "Soybeans": "#2E86AB",
    "Grass/Pasture": "#7DCEA0",
    "Winter Wheat": "#E67E22",
    "Other": "#95A5A6",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_cdl(grower_slug: str) -> pd.DataFrame:
    """Load CDL full composition CSV for a grower."""
    df = pd.read_csv(GROWERS[grower_slug]["cdl"])
    df["grower"] = GROWERS[grower_slug]["label"]
    df["grower_slug"] = grower_slug
    return df


def load_boundaries(grower_slug: str) -> gpd.GeoDataFrame:
    """Load boundary GeoJSON for a grower."""
    return gpd.read_file(GROWERS[grower_slug]["boundary"])


def shannon_diversity(pcts: pd.Series) -> float:
    """Shannon diversity index H' = -sum(p_i * ln(p_i)).
    pcts are proportions (0-100); we normalize to 0-1 inside."""
    props = pcts / 100.0
    props = props[props > 0]
    if len(props) == 0:
        return 0.0
    return -sum(props * np.log(props))


# ---------------------------------------------------------------------------
# 1. Crop Diversity Score line graph
# ---------------------------------------------------------------------------

def plot_diversity_score_line() -> Path:
    """Shannon diversity index per grower per year, 2021-2025."""
    rows = []
    for slug in GROWERS:
        df = load_cdl(slug)
        # Diversity per grower per year: aggregate pixel counts by crop
        yearly = df.groupby(["year", "crop_name"])["pixel_count"].sum().reset_index()
        for year, group in yearly.groupby("year"):
            total_pixels = group["pixel_count"].sum()
            group["pct"] = (group["pixel_count"] / total_pixels) * 100
            h = shannon_diversity(group["pct"])
            rows.append({
                "grower": GROWERS[slug]["label"],
                "year": year,
                "shannon_diversity": round(h, 3),
            })

    div_df = pd.DataFrame(rows)

    plt.figure(figsize=(10, 6))
    sns.set_style("whitegrid")

    palette = {"Illinois": "#2E86AB", "Iowa": "#A23B72", "Nebraska": "#F18F01"}
    order = ["Illinois", "Iowa", "Nebraska"]

    for grower in order:
        subset = div_df[div_df["grower"] == grower]
        plt.plot(
            subset["year"],
            subset["shannon_diversity"],
            marker="o",
            markersize=8,
            linewidth=2.5,
            color=palette[grower],
            label=grower,
        )

    plt.title(
        "Crop Diversity Score (Shannon Index) by Grower\n"
        "(Higher = More Diverse / Lower Rotation Risk)",
        fontsize=14,
        fontweight="bold",
    )
    plt.xlabel("Year", fontsize=12)
    plt.ylabel("Shannon Diversity Index (H')", fontsize=12)
    plt.xticks(sorted(div_df["year"].unique()))
    plt.legend(title="Grower", loc="best")
    plt.ylim(0, div_df["shannon_diversity"].max() * 1.15)
    plt.tight_layout()

    out_path = OUTPUT_DIR / "cdl_diversity_score_line.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out_path.name}")
    return out_path


# ---------------------------------------------------------------------------
# 2. Rotation frequency chart
# ---------------------------------------------------------------------------

def _classify_rotation(crops: list[str]) -> str:
    """Classify a 5-year crop sequence into a rotation pattern."""
    # Dominant crop per year (already aggregated by field_id,year in CDL)
    # But full composition may have multiple crops per field/year.
    # We take the crop with highest pct per year.
    # crops is a list of (year, crop_name, pct) for one field.
    # Simplify: count transitions.
    corn_count = sum(1 for c in crops if c == "Corn")
    soy_count = sum(1 for c in crops if c == "Soybeans")

    if corn_count == len(crops):
        return "Continuous Corn"
    if soy_count == len(crops):
        return "Continuous Soy"
    if corn_count >= 2 and soy_count >= 2:
        return "Corn-Soy Rotation"
    return "Mixed / Other"


def plot_rotation_frequency() -> Path:
    """Stacked bar chart of rotation pattern frequencies per grower."""
    rows = []
    for slug in GROWERS:
        df = load_cdl(slug)
        # Get dominant crop per field per year
        dominant = (
            df.loc[df.groupby(["field_id", "year"])["pct"].idxmax()]
            .sort_values(["field_id", "year"])
            .copy()
        )

        for field_id, group in dominant.groupby("field_id"):
            crops = group.sort_values("year")["crop_name"].tolist()
            pattern = _classify_rotation(crops)
            rows.append({
                "grower": GROWERS[slug]["label"],
                "field_id": field_id,
                "rotation_pattern": pattern,
            })

    rot_df = pd.DataFrame(rows)

    # Count per grower per pattern
    counts = rot_df.groupby(["grower", "rotation_pattern"]).size().reset_index(name="count")
    pivot = counts.pivot(index="grower", columns="rotation_pattern", values="count").fillna(0).astype(int)

    # Ensure column order
    pattern_order = ["Corn-Soy Rotation", "Continuous Corn", "Continuous Soy", "Mixed / Other"]
    for pat in pattern_order:
        if pat not in pivot.columns:
            pivot[pat] = 0
    pivot = pivot[[p for p in pattern_order if p in pivot.columns]]
    pivot = pivot.reindex(["Illinois", "Iowa", "Nebraska"])

    # Colors
    pat_colors = {
        "Corn-Soy Rotation": "#27AE60",
        "Continuous Corn": "#F4D03F",
        "Continuous Soy": "#2E86AB",
        "Mixed / Other": "#95A5A6",
    }
    colors = [pat_colors.get(c, "#95A5A6") for c in pivot.columns]

    ax = pivot.plot(
        kind="bar",
        stacked=True,
        color=colors,
        edgecolor="black",
        linewidth=0.5,
        figsize=(10, 6),
    )

    plt.title(
        "Rotation Pattern Frequency by Grower\n"
        "(Strategic Planting Stability)",
        fontsize=14,
        fontweight="bold",
    )
    plt.xlabel("Grower", fontsize=12)
    plt.ylabel("Number of Fields", fontsize=12)
    plt.xticks(rotation=0)
    plt.legend(title="Rotation Pattern", bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.tight_layout()

    out_path = OUTPUT_DIR / "cdl_rotation_frequency.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out_path.name}")
    return out_path


# ---------------------------------------------------------------------------
# 3. Iowa transition probability matrix
# ---------------------------------------------------------------------------

def compute_iowa_transition_matrix() -> Path:
    """Year-over-year crop transition probabilities for Iowa fields."""
    df = load_cdl("ia-grower")

    # Dominant crop per field per year
    dominant = (
        df.loc[df.groupby(["field_id", "year"])["pct"].idxmax()]
        .sort_values(["field_id", "year"])
        .copy()
    )

    # Build transition pairs
    transitions = []
    for field_id, group in dominant.groupby("field_id"):
        group = group.sort_values("year")
        crops = group["crop_name"].tolist()
        for i in range(len(crops) - 1):
            transitions.append({
                "from_crop": crops[i],
                "to_crop": crops[i + 1],
            })

    trans_df = pd.DataFrame(transitions)

    # Transition counts
    counts = trans_df.groupby(["from_crop", "to_crop"]).size().reset_index(name="count")

    # Probability matrix
    from_totals = counts.groupby("from_crop")["count"].sum().to_dict()
    counts["probability"] = counts.apply(
        lambda row: round(row["count"] / from_totals[row["from_crop"]], 3), axis=1
    )

    pivot = counts.pivot(index="from_crop", columns="to_crop", values="probability").fillna(0)

    out_path = OUTPUT_DIR / "cdl_iowa_transition_matrix.csv"
    pivot.to_csv(out_path)
    print(f"  ✓ {out_path.name}")
    return out_path


# ---------------------------------------------------------------------------
# 4. Dominant CDL geospatial map (3-panel composite)
# ---------------------------------------------------------------------------

def plot_dominant_crop_map() -> Path:
    """Map field boundaries colored by 2025 dominant crop."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 7))

    order = [
        ("Illinois", "il-grower"),
        ("Iowa", "ia-grower"),
        ("Nebraska", "ne-grower"),
    ]

    # Collect all dominant crops for color mapping
    all_dominant: dict[str, str] = {}
    for slug in GROWERS:
        df = load_cdl(slug)
        dominant = df.loc[df.groupby(["field_id", "year"])["pct"].idxmax()].copy()
        dominant_2025 = dominant[dominant["year"] == 2025].copy()
        for _, row in dominant_2025.iterrows():
            all_dominant[row["field_id"]] = row["crop_name"]

    # Build color map for all unique crops
    unique_crops = sorted(set(all_dominant.values()))
    crop_color_map = {}
    for crop in unique_crops:
        crop_color_map[crop] = CROP_COLORS.get(crop, "#95A5A6")

    for ax, (grower_label, slug) in zip(axes, order):
        gdf = load_boundaries(slug).to_crs(epsg=4326)
        gdf["dominant_crop"] = gdf["field_id"].map(all_dominant)

        facecolors = [crop_color_map.get(c, "#95A5A6") for c in gdf["dominant_crop"]]

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

    # Legend patches
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=crop_color_map[c], edgecolor="black", label=c)
        for c in sorted(crop_color_map)
    ]
    fig.legend(
        handles=legend_elements,
        loc="lower center",
        ncol=len(legend_elements),
        bbox_to_anchor=(0.5, -0.02),
        fontsize=10,
        title="2025 Dominant Crop",
        title_fontsize=11,
    )

    fig.suptitle(
        "Field Boundaries Colored by 2025 Dominant CDL Crop\n"
        "(Strategic Planting Decisions at Portfolio Level)",
        fontsize=14,
        fontweight="bold",
        y=1.02,
    )
    plt.tight_layout(rect=[0, 0.03, 1, 1])

    out_path = OUTPUT_DIR / "cdl_dominant_crop_map.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out_path.name}")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("CDL Module — Operational Stability & Risk")
    print("=" * 60)

    _ensure_output_dir()

    print("\n[1/4] Crop diversity score line graph...")
    plot_diversity_score_line()

    print("\n[2/4] Rotation frequency chart...")
    plot_rotation_frequency()

    print("\n[3/4] Iowa transition probability matrix...")
    compute_iowa_transition_matrix()

    print("\n[4/4] Dominant crop geospatial map...")
    plot_dominant_crop_map()

    print(f"\n{'=' * 60}")
    print(f"All outputs saved to: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
