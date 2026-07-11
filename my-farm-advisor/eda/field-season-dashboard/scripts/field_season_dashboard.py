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
import scipy.stats as stats
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
def _ssurgo_summary_path(grower: str, farm: str, field: str) -> Path:
    return _field_dir(grower, farm, field) / "soil" / "ssurgo_summary.csv"


# ---------------------------------------------------------------------------
# SSURGO AWC loading
# ---------------------------------------------------------------------------
def load_ssurgo_awc(grower: str, farm: str, field: str) -> dict[str, Any]:
    """Load SSURGO available water capacity summary for the field."""
    path = _ssurgo_summary_path(grower, farm, field)
    if not path.exists():
        return {"total_aws_inches": None, "drainage_class": None}
    df = pd.read_csv(path)
    if df.empty:
        return {"total_aws_inches": None, "drainage_class": None}
    return {
        "total_aws_inches": float(df.iloc[0]["total_aws_inches"]) if "total_aws_inches" in df.columns else None,
        "drainage_class": str(df.iloc[0]["drainage_class"]) if "drainage_class" in df.columns else None,
    }


# ---------------------------------------------------------------------------
# SPI calculation
# ---------------------------------------------------------------------------
def _gamma_fit_positive(values: np.ndarray) -> tuple[float, float, float]:
    """Fit 2-parameter gamma to positive values, return shape, scale, loc."""
    pos = values[values > 0]
    if len(pos) < 3:
        return np.nan, np.nan, np.nan
    try:
        shape, loc, scale = stats.gamma.fit(pos, floc=0)
        return float(shape), float(scale), float(loc)
    except Exception:
        return np.nan, np.nan, np.nan


def calculate_spi(
    grower: str, farm: str, field: str, target_year: int, window_days: int = 30
) -> pd.DataFrame:
    """Calculate 30-day SPI for the target year using the full available weather archive.

    Uses a gamma distribution fitted per day-of-year (DOY) with a ±14-day window
    across all available years to build a robust climatological reference.
    """
    path = _weather_path(grower, farm, field)
    if not path.exists():
        raise FileNotFoundError(f"Weather file not found: {path}")

    # Load entire archive
    all_weather = pd.read_csv(path, parse_dates=["date"])
    all_weather = all_weather.sort_values("date").reset_index(drop=True)

    # 30-day rolling precipitation sum
    all_weather["P30"] = all_weather["PRECTOTCORR"].rolling(window=window_days, min_periods=window_days).sum()

    # Drop dates where P30 is NaN (first 29 days of the record)
    all_weather = all_weather.dropna(subset=["P30"]).copy()
    all_weather["doy"] = all_weather["date"].dt.dayofyear

    # Build reference distributions per DOY
    doy_models: dict[int, dict[str, Any]] = {}
    all_doys = sorted(all_weather["doy"].unique())

    for doy in range(1, 367):
        # Collect samples within ±14 days of this DOY across all years
        window_doys = [(doy + offset) % 365 or 365 for offset in range(-14, 15)]
        samples = all_weather[all_weather["doy"].isin(window_doys)]["P30"].values

        if len(samples) < 10:
            doy_models[doy] = {"method": "insufficient"}
            continue

        # Mixed distribution: estimate P0 and fit gamma to positives
        zeros = (samples == 0).sum()
        p0 = zeros / len(samples)
        pos_samples = samples[samples > 0]

        if len(pos_samples) < 3:
            doy_models[doy] = {"method": "empirical", "samples": samples}
            continue

        shape, scale, loc = _gamma_fit_positive(pos_samples)
        if np.isnan(shape) or shape <= 0 or scale <= 0:
            doy_models[doy] = {"method": "empirical", "samples": samples}
            continue

        doy_models[doy] = {
            "method": "gamma",
            "p0": p0,
            "shape": shape,
            "scale": scale,
            "loc": loc,
        }

    # Compute SPI for target year
    target = all_weather[all_weather["date"].dt.year == target_year].copy()
    spi_values = []
    for _, row in target.iterrows():
        doy = int(row["doy"])
        p30 = float(row["P30"])
        model = doy_models.get(doy, {"method": "insufficient"})

        if model["method"] == "insufficient":
            spi = np.nan
        elif model["method"] == "empirical":
            samples = model["samples"]
            # Empirical percentile with plotting position
            rank = np.searchsorted(np.sort(samples), p30, side="right")
            cdf = rank / (len(samples) + 1)
            # Avoid exact 0 or 1
            cdf = max(1e-6, min(1 - 1e-6, cdf))
            spi = float(stats.norm.ppf(cdf))
        else:  # gamma
            p0 = model["p0"]
            if p30 == 0:
                cdf = p0
            else:
                cdf = p0 + (1 - p0) * stats.gamma.cdf(p30, model["shape"], loc=model["loc"], scale=model["scale"])
            cdf = max(1e-6, min(1 - 1e-6, cdf))
            spi = float(stats.norm.ppf(cdf))

        spi_values.append(spi)

    target["SPI"] = spi_values
    return target[["date", "PRECTOTCORR", "P30", "SPI"]].copy()


# ---------------------------------------------------------------------------
# SPI event detection
# ---------------------------------------------------------------------------
def detect_spi_events(spi_df: pd.DataFrame) -> dict[str, Any]:
    """Detect significant drought and wetness events from SPI series."""
    events: dict[str, Any] = {
        "drought_onset": None,
        "drought_recovery": None,
        "min_spi": None,
        "wet_spell": None,
    }

    if spi_df.empty or spi_df["SPI"].isna().all():
        return events

    valid = spi_df.dropna(subset=["SPI"]).copy()
    if valid.empty:
        return events

    # Drought onset: first date SPI < -1
    drought = valid[valid["SPI"] < -1.0]
    if not drought.empty:
        events["drought_onset"] = {
            "date": drought.iloc[0]["date"],
            "spi": float(drought.iloc[0]["SPI"]),
        }
        # Recovery: last date before end where SPI goes back above -1
        after_onset = valid[valid["date"] >= drought.iloc[0]["date"]]
        recovered = after_onset[after_onset["SPI"] >= -1.0]
        if not recovered.empty:
            events["drought_recovery"] = {
                "date": recovered.iloc[0]["date"],
                "spi": float(recovered.iloc[0]["SPI"]),
            }

    # Minimum SPI
    min_idx = valid["SPI"].idxmin()
    min_row = valid.loc[min_idx]
    events["min_spi"] = {
        "date": min_row["date"],
        "spi": float(min_row["SPI"]),
    }

    # Wet spell: first date SPI > 1.5
    wet = valid[valid["SPI"] > 1.5]
    if not wet.empty:
        events["wet_spell"] = {
            "date": wet.iloc[0]["date"],
            "spi": float(wet.iloc[0]["SPI"]),
        }

    return events


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
    spi_df: pd.DataFrame,
    spi_events: dict[str, Any],
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

    # SPI narrative
    if not spi_df.empty and not spi_df["SPI"].isna().all():
        min_spi = float(spi_df["SPI"].min())
        max_spi = float(spi_df["SPI"].max())
        spi_notes = []
        if spi_events["drought_onset"]:
            onset = spi_events["drought_onset"]
            spi_notes.append(f"drought onset {onset['date'].strftime('%b %d')} (SPI {onset['spi']:.2f})")
        if spi_events["wet_spell"]:
            wet = spi_events["wet_spell"]
            spi_notes.append(f"wet spell {wet['date'].strftime('%b %d')} (SPI {wet['spi']:.2f})")
        if spi_notes:
            parts.append("SPI context: " + ", ".join(spi_notes) + f". Range {min_spi:.2f} to {max_spi:.2f}.")
        else:
            parts.append(f"SPI remained near normal (range {min_spi:.2f} to {max_spi:.2f}).")

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
    spi_df: pd.DataFrame,
    spi_events: dict[str, Any],
    awc: dict[str, Any],
) -> Path:
    """Render the multi-panel dashboard and save as PNG."""
    # Filter weather to growing season for display
    gs_start = pd.Timestamp(f"{year}-{_GS_START_MONTH_DAY[0]:02d}-{_GS_START_MONTH_DAY[1]:02d}")
    gs_end = pd.Timestamp(f"{year}-{_GS_END_MONTH_DAY[0]:02d}-{_GS_END_MONTH_DAY[1]:02d}")
    wdisp = weather[(weather["date"] >= gs_start) & (weather["date"] <= gs_end)].copy()

    fig = plt.figure(figsize=(16, 14))
    gs = fig.add_gridspec(
        nrows=7,
        ncols=1,
        height_ratios=[0.08, 1.0, 1.0, 1.0, 1.0, 1.0, 0.12],
        hspace=0.35,
        left=0.08,
        right=0.82,
        top=0.94,
        bottom=0.06,
    )

    # ---- Header -----------------------------------------------------------
    ax_header = fig.add_subplot(gs[0])
    ax_header.axis("off")
    total_precip = float(wdisp["PRECTOTCORR"].sum()) if not wdisp.empty else 0.0
    peak_ndvi = float(ndvi["mean_ndvi"].max()) if not ndvi.empty else 0.0
    total_gdd = float(wdisp["CUM_GDD"].iloc[-1]) if not wdisp.empty else 0.0
    min_spi = float(spi_df["SPI"].min()) if not spi_df.empty and not spi_df["SPI"].isna().all() else np.nan
    header_text = (
        f"Field: {field}  |  Year: {year}  |  Crop: {crop_name}  |  "
        f"Total Precip: {total_precip:.1f} mm  |  Peak NDVI: {peak_ndvi:.2f}  |  "
        f"Cum GDD: {total_gdd:.0f}  |  Min SPI: {min_spi:.2f}"
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
        # Cool periods — add legend proxy first
        ax_temp.axvspan(
            pd.Timestamp.min, pd.Timestamp.min, color="#5DADE2", alpha=0.15,
            label="Cool period (≥3d <10°C max)",
        )
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
    ax_temp.legend(
        loc="upper left",
        bbox_to_anchor=(1.02, 1.0),
        borderaxespad=0,
        framealpha=0.9,
    )
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

    # ---- SPI panel --------------------------------------------------------
    ax_spi = fig.add_subplot(gs[5], sharex=ax_ndvi)
    spi_disp = spi_df[(spi_df["date"] >= gs_start) & (spi_df["date"] <= gs_end)].copy()
    if not spi_disp.empty:
        # Background drought/wet bands
        ax_spi.axhspan(-3.0, -2.0, color="#C0392B", alpha=0.12, label="Extreme drought")
        ax_spi.axhspan(-2.0, -1.5, color="#E67E22", alpha=0.12, label="Severe drought")
        ax_spi.axhspan(-1.5, -1.0, color="#F1C40F", alpha=0.12, label="Moderate drought")
        ax_spi.axhspan(1.0, 1.5, color="#5DADE2", alpha=0.12, label="Moderately wet")
        ax_spi.axhspan(1.5, 2.0, color="#2E86AB", alpha=0.12, label="Very wet")
        ax_spi.axhspan(2.0, 3.0, color="#1B4F72", alpha=0.12, label="Extremely wet")

        # Reference lines
        for y in [-2.0, -1.5, -1.0, 0.0, 1.0, 1.5, 2.0]:
            ax_spi.axhline(y, color="#7F8C8D", linestyle="--", alpha=0.5, lw=0.6)

        # SPI line
        ax_spi.plot(
            spi_disp["date"], spi_disp["SPI"],
            color="#8E44AD", linewidth=1.5, label="SPI (30-day)",
        )

        # Annotations for significant events
        if spi_events["drought_onset"]:
            ev = spi_events["drought_onset"]
            if gs_start <= ev["date"] <= gs_end:
                ax_spi.annotate(
                    f"drought onset\n{ev['spi']:.2f}",
                    xy=(ev["date"], ev["spi"]),
                    xytext=(0, -28),
                    textcoords="offset points",
                    ha="center", fontsize=7, color="#C0392B",
                    arrowprops=dict(arrowstyle="->", color="#C0392B", lw=0.8),
                )

        if spi_events["drought_recovery"]:
            ev = spi_events["drought_recovery"]
            if gs_start <= ev["date"] <= gs_end:
                ax_spi.annotate(
                    f"recovery\n{ev['spi']:.2f}",
                    xy=(ev["date"], ev["spi"]),
                    xytext=(0, 18),
                    textcoords="offset points",
                    ha="center", fontsize=7, color="#27AE60",
                    arrowprops=dict(arrowstyle="->", color="#27AE60", lw=0.8),
                )

        if spi_events["min_spi"]:
            ev = spi_events["min_spi"]
            if gs_start <= ev["date"] <= gs_end:
                ax_spi.annotate(
                    f"min SPI {ev['spi']:.2f}",
                    xy=(ev["date"], ev["spi"]),
                    xytext=(0, -18),
                    textcoords="offset points",
                    ha="center", fontsize=7, color="#E74C3C",
                    arrowprops=dict(arrowstyle="->", color="#E74C3C", lw=0.8),
                )

        if spi_events["wet_spell"]:
            ev = spi_events["wet_spell"]
            if gs_start <= ev["date"] <= gs_end:
                ax_spi.annotate(
                    f"wet spell\n{ev['spi']:.2f}",
                    xy=(ev["date"], ev["spi"]),
                    xytext=(0, 18),
                    textcoords="offset points",
                    ha="center", fontsize=7, color="#2980B9",
                    arrowprops=dict(arrowstyle="->", color="#2980B9", lw=0.8),
                )

        # AWC context note
        if awc.get("total_aws_inches") is not None:
            aws = awc["total_aws_inches"]
            drain = awc.get("drainage_class", "")
            note = f"AWC: {aws:.1f} in/ft"
            if drain:
                note += f"  |  {drain}"
            ax_spi.text(
                0.98, 0.02, note,
                transform=ax_spi.transAxes,
                ha="right", va="bottom",
                fontsize=7, color="#555555",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="#F8F9F9", edgecolor="#BDC3C7", alpha=0.8),
            )
    else:
        ax_spi.text(0.5, 0.5, "No SPI data available", transform=ax_spi.transAxes, ha="center", va="center")

    ax_spi.set_ylabel("SPI")
    ax_spi.set_title("30-Day Standardized Precipitation Index (SPI)")
    ax_spi.set_ylim(-3.0, 3.0)
    ax_spi.legend(
        loc="upper left",
        bbox_to_anchor=(1.02, 1.0),
        borderaxespad=0,
        ncol=1,
        framealpha=0.9,
    )
    ax_spi.grid(True, alpha=0.3)

    # SPI annotation box — positioned to the right of the legend
    ax_spi.text(
        1.20, 0.48,
        "30-day SPI from field daily precip.\n"
        "Gamma distribution per DOY\n"
        "(±14d window, 5-yr archive)\n"
        "→ standard normal transform.",
        transform=ax_spi.transAxes,
        ha="left", va="top",
        fontsize=6.5, color="#555555",
        linespacing=1.2,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#F8F9F9", edgecolor="#BDC3C7", alpha=0.85),
    )

    # AWC metric explanation — to the right of the legend, below method annotation
    ax_spi.text(
        1.20, 0.22,
        "AWC = SSURGO soil water capacity\n"
        "(inches water / foot of soil).\n"
        "Lower value → higher drought risk.\n"
        "Source: USDA NRCS SSURGO.",
        transform=ax_spi.transAxes,
        ha="left", va="top",
        fontsize=6.5, color="#555555",
        linespacing=1.2,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#F8F9F9", edgecolor="#BDC3C7", alpha=0.85),
    )

    # Format x-axis for all shared axes
    for ax in [ax_ndvi, ax_precip, ax_temp, ax_gdd, ax_spi]:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=0)

    # ---- Footer caption ---------------------------------------------------
    ax_footer = fig.add_subplot(gs[6])
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

    # 4. Load SSURGO AWC
    awc = load_ssurgo_awc(args.grower, args.farm, args.field)
    if awc["total_aws_inches"] is not None:
        print(f"SSURGO AWC: {awc['total_aws_inches']:.1f} in/ft")

    # 5. Calculate SPI
    spi_df = calculate_spi(args.grower, args.farm, args.field, args.year)
    spi_events = detect_spi_events(spi_df)
    print(f"SPI computed: {len(spi_df)} days, min SPI: {spi_df['SPI'].min():.2f}")
    if spi_events["drought_onset"]:
        print(f"  Drought onset: {spi_events['drought_onset']['date'].strftime('%Y-%m-%d')} (SPI {spi_events['drought_onset']['spi']:.2f})")
    if spi_events["min_spi"]:
        print(f"  Min SPI: {spi_events['min_spi']['date'].strftime('%Y-%m-%d')} (SPI {spi_events['min_spi']['spi']:.2f})")

    if args.dry_run:
        print("Dry-run complete. Inputs validated.")
        return

    # 6. Detect events
    w_events = detect_weather_events(weather)
    n_events = detect_ndvi_events(ndvi)
    print(f"Weather events: {len(w_events['heavy_rain'])} heavy rain, {len(w_events['hot_days'])} hot days, {len(w_events['cool_periods'])} cool periods")
    print(f"NDVI events: {len(n_events['dips'])} dips, {len(n_events['rapid_increases'])} rapid increases")

    # 7. Generate caption
    caption = generate_seasonal_caption(
        crop_info["crop_name"], args.year, weather, ndvi, w_events, n_events, missing_months, spi_df, spi_events
    )
    print(f"Caption: {caption}")

    # 8. Render
    out_path = render_dashboard(
        args.grower, args.farm, args.field, args.year,
        crop_info["crop_name"], weather, ndvi, w_events, n_events, missing_months, caption,
        spi_df, spi_events, awc,
    )
    print(f"Done: {out_path}")


if __name__ == "__main__":
    main()
