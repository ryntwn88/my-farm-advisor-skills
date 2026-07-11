---
name: field-season-dashboard-guide
description: Step-by-step workflow guide for the Field Season Dashboard skill. Generates an aligned NDVI + weather + CDL dashboard for a single field-year.
version: 1.0.0
author: my-farm-advisor
---

# Field Season Dashboard — Workflow Guide

## Narrative Arc

> **CDL sets the crop context** → **Daily weather drives the season** → **Sentinel NDVI reveals vegetation response** → **SPI exposes drought/wetness stress** → **Annotations highlight the critical moments**. Together they answer: what happened this season and why?

## Prerequisites

```bash
export DATA_PIPELINE_DATA_ROOT="/home/coder/my-farm-advisor-runtime/data-pipeline"
```

Ensure the runtime has:
- `daily_weather.csv` for the target field (multi-year archive for SPI climatology)
- Sentinel manifest and NDVI scenes for the target year
- `ndvi_year_crop_join.csv` with CDL crop assignments
- `soil/ssurgo_summary.csv` for AWC context (optional but recommended)

## Step-by-Step

### 1. Confirm the field-year inputs

```bash
cd ${DATA_PIPELINE_DATA_ROOT}/src
python ~/my-farm-advisor-skills/my-farm-advisor/eda/field-season-dashboard/scripts/field_season_dashboard.py \
  --grower ia-grower \
  --farm ia-grower-iowa \
  --field osm-1360326425 \
  --year 2025 \
  --dry-run
```

This prints the detected CDL crop and confirms data availability without rendering.

### 2. Generate the dashboard

```bash
cd ${DATA_PIPELINE_DATA_ROOT}/src
python ~/my-farm-advisor-skills/my-farm-advisor/eda/field-season-dashboard/scripts/field_season_dashboard.py \
  --grower ia-grower \
  --farm ia-grower-iowa \
  --field osm-1360326425 \
  --year 2025
```

Output path:
```
growers/ia-grower/farms/ia-grower-iowa/fields/osm-1360326425/derived/reports/field_season_dashboard_2025.png
```

### 3. Reuse for another field-year

Change the four CLI arguments to target any field and year in the runtime.

## CLI Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--grower` | `ia-grower` | Grower slug |
| `--farm` | `ia-grower-iowa` | Farm slug |
| `--field` | `osm-1360326425` | Field slug |
| `--year` | `2025` | Growing season year |
| `--dry-run` | `False` | Validate inputs only, skip rendering |

## Design Decisions

- **Static PNG only** — no interactive dashboard, matching existing reporting conventions.
- **Shared date axis** — all panels aligned vertically so advisors can correlate events across NDVI and weather at a glance.
- **Explicit missing-coverage notice** — if Sentinel scenes are missing early-season months, the NDVI panel prints a clear annotation rather than interpolating.
- **Event detection thresholds**:
  - Heavy rain: daily precipitation ≥ 25 mm
  - Hot day: daily max temperature ≥ 32 °C
  - Cool period: ≥ 3 consecutive days with daily max < 10 °C
  - NDVI dip: drop > 0.10 between consecutive observations
  - Rapid NDVI increase: rise > 0.10 between consecutive observations
- **GDD calculation** — base 10 °C: `max(0, (T2M_MAX + T2M_MIN)/2 - 10)`
- **Growing season filter** — April 1 through October 31 for weather panels; NDVI uses all available scenes for the year.
- **SPI calculation** — 30-day Standardized Precipitation Index computed per day-of-year (DOY) using gamma distribution fitting:
  1. Compute 30-day rolling precipitation sum for every date in the full weather archive.
  2. For each DOY, build a reference sample from that DOY ±14 days across all available years (≈150 samples with 5 years of data).
  3. Fit a 2-parameter gamma distribution (MLE) to positive values; estimate zero-probability fraction for mixed-distribution correction.
  4. Map the target year's observed 30-day total to a cumulative probability under the fitted gamma.
  5. Transform to standard normal: `SPI = Φ⁻¹(cumulative_probability)`.
  6. Fallback to empirical percentile → normal transformation if gamma fitting fails.
- **SPI panel drought/wet bands** — background color zones aligned with standard SPI categories:
  - Extreme drought: SPI ≤ −2 (red)
  - Severe drought: −2 < SPI ≤ −1.5 (orange)
  - Moderate drought: −1.5 < SPI ≤ −1 (yellow)
  - Moderately wet: +1 ≤ SPI < +1.5 (light blue)
  - Very wet: +1.5 ≤ SPI < +2 (darker blue)
  - Extremely wet: SPI ≥ +2 (darkest blue)
- **SSURGO AWC context** — if `ssurgo_summary.csv` is available, the SPI panel displays the field's total available water capacity (in/ft) and drainage class to help advisors interpret drought severity in the context of soil water-holding capacity.

## Outputs

- `field_season_dashboard_{year}.png` — the aligned dashboard image
