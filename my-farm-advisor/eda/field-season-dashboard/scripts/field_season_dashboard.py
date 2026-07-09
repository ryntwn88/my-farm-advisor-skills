#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportArgumentType=false, reportCallIssue=false, reportGeneralTypeIssues=false
# ruff: noqa: I001
"""Generate a single-image field-season dashboard combining Sentinel NDVI,
daily weather, and CDL crop-year information for one field and one growing season.

Usage:
    python field_season_dashboard.py \
        --grower ia-grower \
        --farm ia-grower-iowa \
        --field osm-1360326425 \
        --year 2025

Output:
    {field_dir}/derived/reports/field_season_dashboard_{year}.png
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask

matplotlib.use("Agg")

# ---------------------------------------------------------------------------
# Runtime path resolution
# ---------------------------------------------------------------------------
_RUNTIME_BASE = Path(os.environ.get("DATA_PIPELINE_DATA_ROOT", "/home/coder/my-farm-advisor-runtime/data-pipeline"))
_GROWERS_ROOT = _RUNTIME_BASE / "growers"
_SHARED_ROOT = _RUNTIME_BASE / "shared"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEFAULT_GROWER = "ia-grower"
_DEFAULT_FARM = "ia-grower-iowa"
_DEFAULT_FIELD = "osm-1360326425"
_DEFAULT_YEAR = 2025

# Event thresholds
_HEAVY_RAIN_MM = 25.0
_HOT_DAY_C = 32.0
_COOL_MAX_C = 10.0
_COOL_CONSECUTIVE_DAYS = 3
_NDVI_DIP = 0.10
_NDVI_RAPID_RISE = 0.10
_GDD_BASE_C = 10.0

# Growing season date filter (for weather panels)
_GS_START_MONTH_DAY = (4, 1)   # Apr 1
_GS_END_MONTH_DAY = (10, 31)   # Oct 31

# Plot styling
plt.rcParams.update({
    "font.size": 9,
    "axes.labelsize": 9,
    "axes.titlesize": 10,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
})


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
def _field_dir(grower: str, farm: str, field: str) -> Path:
    return _GROWERS_ROOT / grower / "farms" / farm / "fields" / field


def _weather_path(grower: str, farm: str, field: str) -> Path:
    return _field_dir(grower, farm, field) / "weather" / "daily_weather.csv"


def _boundary_path(grower: str, farm: str, field: str) -> Path:
    return _field_dir(grower, farm, field) / "boundary" / "field_boundary.geojson"


def _sentinel_manifest_path(grower: str, farm: str, field: str) -> Path:
    return _field_dir(grower, farm, field) / "satellite" / "sentinel" / "manifest.json"


def _crop_join_path(grower: str, farm: str, field: str) -> Path:
    return _field_dir(grower, farm, field) / "derived" / "tables" / "ndvi_year_crop_join.csv"


def _reports_dir(grower: str, farm: str, field: str) -> Path:
    d = _field_dir(grower, farm, field) / "derived" / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_crop_year(grower: str, farm: str, field: str, year: int) -> dict[str, Any]:
    """Load CDL crop assignment for the target year."""
    path = _crop_join_path(grower, farm, field)
    if not path.exists():
        raise FileNotFoundError(f"Crop join table not found: {path}")
    df = pd.read_csv(path)
    row = df[(df["field_slug"] == field) & (df["year"] == year)]
    if row.empty:
        raise ValueError(f"No CDL crop entry for {field} year {year}")
    return {
        "crop_name": row.iloc[0]["crop_name"],
        "scene_count": int(row.iloc[0]["scene_count"]),
        "composite_tif": row.iloc[0].get("composite_tif", None),
    }


def load_weather(grower: str, farm: str, field: str, year: int) -> pd.DataFrame:
    """Load daily weather for the target year."""
    path = _weather_path(grower, farm, field)
    if not path.exists():
        raise FileNotFoundError(f"Weather file not found: {path}")
    df = pd.read_csv(path, parse_dates=["date"])
    df = df[df["date"].dt.year == year].copy()
    if df.empty:
        raise ValueError(f"No weather data for year {year}")
    df = df.sort_values("date").reset_index(drop=True)
    # GDD
    t_avg = (df["T2M_MAX"] + df["T2M_MIN"]) / 2.0
    df["GDD"] = np.maximum(0.0, t_avg - _GDD_BASE_C)
    df["CUM_GDD"] = df["GDD"].cumsum()
    return df


def load_sentinel_ndvi_series(
    grower: str, farm: str, field: str, year: int
) -> tuple[pd.DataFrame, list[int]]:
    """Load Sentinel NDVI scenes and compute per-scene mean NDVI masked to field boundary."""
    manifest_path = _sentinel_manifest_path(grower, farm, field)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Sentinel manifest not found: {manifest_path}")

    with open(manifest_path) as f:
        manifest = json.load(f)

    year_data = None
    for y in manifest.get("years", []):
        if y["year"] == year:
            year_data = y
            break

    if year_data is None:
        raise ValueError(f"No Sentinel manifest entry for year {year}")

    scenes = year_data.get("scenes", [])
    if not scenes:
        raise ValueError(f"No Sentinel scenes for year {year}")

    boundary = gpd.read_file(_boundary_path(grower, farm, field))
    boundary = boundary.to_crs(epsg=4326)
    geom = [boundary.geometry.union_all().__geo_interface__]

    records = []
    for scene in scenes:
        ndvi_rel = scene.get("ndvi_tif")
        if not ndvi_rel:
            continue
        ndvi_path = _RUNTIME_BASE / ndvi_rel
        if not ndvi_path.exists():
            continue
        try:
            with rasterio.open(ndvi_path) as src:
                out_image, out_transform = mask(src, geom, crop=True, all_touched=True, filled=False)
                ndvi = out_image[0]
                # Mask invalids
                valid = ndvi > -1.0
                if valid.any():
                    mean_ndvi = float(ndvi[valid].mean())
                else:
                    mean_ndvi = np.nan
            records.append({
                "date": pd.Timestamp(scene["scene_date"]),
                "mean_ndvi": mean_ndvi,
                "cloud_cover": scene.get("cloud_cover", np.nan),
            })
        except Exception:
            continue

    df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
    missing_months = year_data.get("missing_months", [])
    return df, missing_months


# ---------------------------------------------------------------------------
# Event detection
# ---------------------------------------------------------------------------
def detect_weather_events(weather: pd.DataFrame) -> dict[str, Any]:
    """Detect heavy rain, hot days, and cool periods."""
    events: dict[str, Any] = {
        "heavy_rain": [],
        "hot_days": [],
        "cool_periods": [],
    }

    # Heavy rain
    heavy = weather[weather["PRECTOTCORR"] >= _HEAVY_RAIN_MM]
    for _, row in heavy.iterrows():
        events["heavy_rain"].append({
            "date": row["date"],
            "value": float(row["PRECTOTCORR"]),
        })

    # Hot days
    hot = weather[weather["T2M_MAX"] >= _HOT_DAY_C]
    for _, row in hot.iterrows():
        events["hot_days"].append({
            "date": row["date"],
            "value": float(row["T2M_MAX"]),
        })

    # Cool periods: consecutive days with T2M_MAX < _COOL_MAX_C
    cool_mask = weather["T2M_MAX"] < _COOL_MAX_C
    in_streak = False
    streak_start = None
    streak_count = 0
    for idx, is_cool in cool_mask.items():
        if is_cool:
            if not in_streak:
                streak_start = weather.loc[idx, "date"]
                in_streak = True
            streak_count += 1
        else:
            if in_streak and streak_count >= _COOL_CONSECUTIVE_DAYS:
                events["cool_periods"].append({
                    "start": streak_start,
                    "end": weather.loc[idx - 1, "date"],
                    "days": streak_count,
                })
            in_streak = False
            streak_count = 0
    # Handle trailing streak
    if in_streak and streak_count >= _COOL_CONSECUTIVE_DAYS:
        events["cool_periods"].append({
            "start": streak_start,
            "end": weather.iloc[-1]["date"],
            "days": streak_count,
        })

    return events


def detect_ndvi_events(ndvi: pd.DataFrame) -> dict[str, Any]:
    """Detect NDVI dips and rapid increases between consecutive observations."""
    events: dict[str, Any] = {
        "dips": [],
        "rapid_increases": [],
    }
    if len(ndvi) < 2:
        return events

    for i in range(1, len(ndvi)):
        prev = ndvi.iloc[i - 1]
        curr = ndvi.iloc[i]
        delta = curr["mean_ndvi"] - prev["mean_ndvi"]
        if delta <= -_NDVI_DIP:
            events["dips"].append({
                "date": curr["date"],
                "prev_date": prev["date"],
                "delta": float(delta),
                "ndvi": float(curr["mean_ndvi"]),
            })
        elif delta >= _NDVI_RAPID_RISE:
            events["rapid_increases"].append({
                "date": curr["date"],
                "prev_date": prev["date"],
                "delta": float(delta),
                "ndvi": float(curr["mean_ndvi"]),
            })
    return events


# ---------------------------------------------------------------------------
# Caption generation
# ---------------------------------------------------------------------------
def generate_seasonal_caption(
    crop_name: str,
    year: int,
    weather: pd.DataFrame,
    ndvi: pd.DataFrame,
    w_events: dict[str, Any],
    n_events: dict[str, Any],
    missing_months: list[int],
) -> str:
    """Generate a short seasonal narrative caption."""
    total_precip = float(weather["PRECTOTCORR"].sum())
    avg_temp = float(weather["T2M"].mean())
    peak_ndvi = float(ndvi["mean_ndvi"].max()) if not ndvi.empty else 0.0
    total_gdd = float(weather["CUM_GDD"].iloc[-1]) if not weather.empty else 0.0

    parts: list[str] = []
    parts.append(
        f"{year} {crop_name} season: {total_precip:.1f} mm total precip, "
        f"{avg_temp:.1f}°C avg temp, {total_gdd:.0f} cumulative GDD."
    )

    event_notes: list[str] = []
    if w_events["heavy_rain"]:
        event_notes.append(f"{len(w_events['heavy_rain'])} heavy-rain day(s)")
    if w_events["hot_days"]:
        event_notes.append(f"{len(w_events['hot_days'])} hot day(s)")
    if w_events["cool_periods"]:
        event_notes.append(f"{len(w_events['cool_periods'])} cool period(s)")
    if n_events["dips"]:
        event_notes.append(f"{len(n_events['dips'])} NDVI dip(s)")
    if n_events["rapid_increases"]:
        event_notes.append(f"{len(n_events['rapid_increases'])} rapid green-up(s)")

    if event_notes:
        parts.append("Notable events: " + ", ".join(event_notes) + ".")

    if missing_months:
        months_str = ", ".join(f"{m:02d}" for m in sorted(missing_months))
        parts.append(f"Note: Sentinel coverage gaps in months {months_str}.")

    if peak_ndvi > 0:
        parts.append(f"Peak NDVI reached {peak_ndvi:.2f}.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Dashboard rendering
# ---------------------------------------------------------------------------
def render_dashboard(
    grower: str,
    farm: str,
    field: str,
    year: int,
    crop_name: str,
    weather: pd.DataFrame,
    ndvi: pd.DataFrame,
    w_events: dict[str, Any],
    n_events: dict[str, Any],
    missing_months: list[int],
    caption: str,
) -> Path:
    """Render the multi-panel dashboard and save as PNG."""
    # Filter weather to growing season for display
    gs_start = pd.Timestamp(f"{year}-{_GS_START_MONTH_DAY[0]:02d}-{_GS_START_MONTH_DAY[1]:02d}")
    gs_end = pd.Timestamp(f"{year}-{_GS_END_MONTH_DAY[0]:02d}-{_GS_END_MONTH_DAY[1]:02d}")
    wdisp = weather[(weather["date"] >= gs_start) & (weather["date"] <= gs_end)].copy()

    fig = plt.figure(figsize=(14, 12))
    gs = fig.add_gridspec(
        nrows=6,
        ncols=1,
        height_ratios=[0.08, 1.0, 1.0, 1.0, 1.0, 0.12],
        hspace=0.35,
        left=0.08,
        right=0.92,
        top=0.94,
        bottom=0.06,
    )

    # ---- Header -----------------------------------------------------------
    ax_header = fig.add_subplot(gs[0])
    ax_header.axis("off")
    total_precip = float(wdisp["PRECTOTCORR"].sum()) if not wdisp.empty else 0.0
    peak_ndvi = float(ndvi["mean_ndvi"].max()) if not ndvi.empty else 0.0
    total_gdd = float(wdisp["CUM_GDD"].iloc[-1]) if not wdisp.empty else 0.0
    header_text = (
        f"Field: {field}  |  Year: {year}  |  Crop: {crop_name}  |  "
        f"Total Precip: {total_precip:.1f} mm  |  Peak NDVI: {peak_ndvi:.2f}  |  "
        f"Cum GDD: {total_gdd:.0f}"
    )
    ax_header.text(
        0.5, 0.5, header_text,
        transform=ax_header.transAxes,
        ha="center", va="center",
        fontsize=11, fontweight="bold",
    )

    # ---- NDVI panel -------------------------------------------------------
    ax_ndvi = fig.add_subplot(gs[1])
    if not ndvi.empty:
        ax_ndvi.plot(
            ndvi["date"], ndvi["mean_ndvi"],
            marker="o", markersize=5, linestyle="-", color="#2E8B57", linewidth=1.5,
            label="Sentinel NDVI",
        )
        # Annotate dips
        for ev in n_events["dips"]:
            ax_ndvi.annotate(
                f"dip\n{ev['delta']:.2f}",
                xy=(ev["date"], ev["ndvi"]),
                xytext=(0, -25),
                textcoords="offset points",
                ha="center", fontsize=7, color="#C0392B",
                arrowprops=dict(arrowstyle="->", color="#C0392B", lw=0.8),
            )
        # Annotate rapid increases
        for ev in n_events["rapid_increases"]:
            ax_ndvi.annotate(
                f"+{ev['delta']:.2f}",
                xy=(ev["date"], ev["ndvi"]),
                xytext=(0, 18),
                textcoords="offset points",
                ha="center", fontsize=7, color="#27AE60",
                arrowprops=dict(arrowstyle="->", color="#27AE60", lw=0.8),
            )
    else:
        ax_ndvi.text(0.5, 0.5, "No NDVI data available", transform=ax_ndvi.transAxes, ha="center", va="center")

    if missing_months:
        months_str = ", ".join(f"{m:02d}" for m in sorted(missing_months))
        ax_ndvi.text(
            0.02, 0.95,
            f"Missing Sentinel coverage: months {months_str}",
            transform=ax_ndvi.transAxes,
            ha="left", va="top",
            fontsize=8, color="#E67E22",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#FEF5E7", edgecolor="#E67E22"),
        )

    ax_ndvi.set_ylabel("NDVI")
    ax_ndvi.set_title("Sentinel NDVI")
    ax_ndvi.set_xlim(gs_start, gs_end)
    ax_ndvi.set_ylim(0.0, 1.0)
    ax_ndvi.grid(True, alpha=0.3)

    # ---- Precipitation panel ----------------------------------------------
    ax_precip = fig.add_subplot(gs[2], sharex=ax_ndvi)
    if not wdisp.empty:
        ax_precip.bar(
            wdisp["date"], wdisp["PRECTOTCORR"],
            width=1.0, color="#3498DB", alpha=0.7, label="Daily precip",
        )
        for ev in w_events["heavy_rain"]:
            ev_date = ev["date"]
            if gs_start <= ev_date <= gs_end:
                ax_precip.axvline(ev_date, color="#C0392B", linestyle="--", alpha=0.5, lw=0.8)
                ax_precip.annotate(
                    f"{ev['value']:.1f} mm",
                    xy=(ev_date, ev["value"]),
                    xytext=(0, 10),
                    textcoords="offset points",
                    ha="center", fontsize=7, color="#C0392B",
                )
    ax_precip.set_ylabel("Precipitation (mm)")
    ax_precip.set_title("Daily Precipitation")
    ax_precip.grid(True, alpha=0.3)

    # ---- Temperature panel ------------------------------------------------
    ax_temp = fig.add_subplot(gs[3], sharex=ax_ndvi)
    if not wdisp.empty:
        ax_temp.fill_between(
            wdisp["date"], wdisp["T2M_MIN"], wdisp["T2M_MAX"],
            alpha=0.25, color="#E67E22", label="Min–Max range",
        )
        ax_temp.plot(
            wdisp["date"], wdisp["T2M"],
            color="#D35400", linewidth=1.2, label="Avg temp",
        )
        # Hot days — add legend proxy first
        ax_temp.plot(
            [], [], color="#C0392B", linestyle="--", alpha=0.4, lw=0.8,
            label="Hot day (≥32°C)",
        )
        for ev in w_events["hot_days"]:
            ev_date = ev["date"]
            if gs_start <= ev_date <= gs_end:
                ax_temp.axvline(ev_date, color="#C0392B", linestyle="--", alpha=0.4, lw=0.8)
        # Cool periods
        for ev in w_events["cool_periods"]:
            start, end = ev["start"], ev["end"]
            if start < gs_start:
                start = gs_start
            if end > gs_end:
                end = gs_end
            if start <= end:
                ax_temp.axvspan(start, end, color="#5DADE2", alpha=0.15)
                mid = start + (end - start) / 2
                ax_temp.annotate(
                    f"cool ({ev['days']}d)",
                    xy=(mid, ax_temp.get_ylim()[0]),
                    xytext=(0, 5),
                    textcoords="offset points",
                    ha="center", fontsize=7, color="#21618C",
                )
    ax_temp.set_ylabel("Temperature (°C)")
    ax_temp.set_title("Temperature (Min / Avg / Max)")
    ax_temp.legend(loc="upper right")
    ax_temp.grid(True, alpha=0.3)

    # ---- Cumulative GDD panel ---------------------------------------------
    ax_gdd = fig.add_subplot(gs[4], sharex=ax_ndvi)
    if not wdisp.empty:
        ax_gdd.plot(
            wdisp["date"], wdisp["CUM_GDD"],
            color="#8E44AD", linewidth=1.8, label="Cumulative GDD",
        )
        ax_gdd.fill_between(
            wdisp["date"], 0, wdisp["CUM_GDD"],
            alpha=0.1, color="#8E44AD",
        )
    ax_gdd.set_ylabel("Cumulative GDD")
    ax_gdd.set_title(f"Cumulative Growing Degree Days (base {_GDD_BASE_C:.0f}°C)")
    ax_gdd.legend(loc="upper left")
    ax_gdd.grid(True, alpha=0.3)

    # Format x-axis for all shared axes
    for ax in [ax_ndvi, ax_precip, ax_temp, ax_gdd]:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=0)

    # ---- Footer caption ---------------------------------------------------
    ax_footer = fig.add_subplot(gs[5])
    ax_footer.axis("off")
    ax_footer.text(
        0.5, 0.5, caption,
        transform=ax_footer.transAxes,
        ha="center", va="center",
        fontsize=9, style="italic",
        wrap=True,
    )

    # Save
    out_dir = _reports_dir(grower, farm, field)
    out_path = out_dir / f"field_season_dashboard_{year}.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Dashboard saved: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Field Season Dashboard")
    parser.add_argument("--grower", default=_DEFAULT_GROWER)
    parser.add_argument("--farm", default=_DEFAULT_FARM)
    parser.add_argument("--field", default=_DEFAULT_FIELD)
    parser.add_argument("--year", type=int, default=_DEFAULT_YEAR)
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs only")
    args = parser.parse_args()

    print(f"Field Season Dashboard — {args.field} / {args.year}")
    print("-" * 50)

    # 1. Confirm crop-year
    crop_info = load_crop_year(args.grower, args.farm, args.field, args.year)
    print(f"CDL crop: {crop_info['crop_name']} (scenes: {crop_info['scene_count']})")

    # 2. Load weather
    weather = load_weather(args.grower, args.farm, args.field, args.year)
    print(f"Weather records: {len(weather)} days")

    # 3. Load NDVI
    ndvi, missing_months = load_sentinel_ndvi_series(args.grower, args.farm, args.field, args.year)
    print(f"NDVI observations: {len(ndvi)} scenes")
    if missing_months:
        print(f"Missing Sentinel months: {sorted(missing_months)}")

    if args.dry_run:
        print("Dry-run complete. Inputs validated.")
        return

    # 4. Detect events
    w_events = detect_weather_events(weather)
    n_events = detect_ndvi_events(ndvi)
    print(f"Weather events: {len(w_events['heavy_rain'])} heavy rain, {len(w_events['hot_days'])} hot days, {len(w_events['cool_periods'])} cool periods")
    print(f"NDVI events: {len(n_events['dips'])} dips, {len(n_events['rapid_increases'])} rapid increases")

    # 5. Generate caption
    caption = generate_seasonal_caption(
        crop_info["crop_name"], args.year, weather, ndvi, w_events, n_events, missing_months
    )
    print(f"Caption: {caption}")

    # 6. Render
    out_path = render_dashboard(
        args.grower, args.farm, args.field, args.year,
        crop_info["crop_name"], weather, ndvi, w_events, n_events, missing_months, caption,
    )
    print(f"Done: {out_path}")


if __name__ == "__main__":
    main()
