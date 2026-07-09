# Field Season Dashboard

A reusable, single-image dashboard that aligns Sentinel NDVI, daily weather, and CDL crop-year information for one field and one growing season.

## Purpose

Farm advisors need a fast, repeatable way to read the seasonal story of a field: how weather drove vegetation patterns, when stress or growth spikes occurred, and what the cumulative heat picture looked like. This skill produces a single PNG with a shared date axis so advisors can scan top-to-bottom and immediately grasp the season.

## What it produces

- A multi-panel static PNG dashboard saved to the field's `derived/reports/` directory.
- Panels: header info, NDVI time series, daily precipitation, temperature min/max/avg, cumulative GDD.
- Auto-detected and annotated events: heavy rain, hot days, cool periods, NDVI dips, rapid NDVI increases.
- A short generated seasonal caption at the bottom.

## Data sources

All inputs are read from the approved data-pipeline runtime:

| Input | Source |
|-------|--------|
| Daily weather | `{field}/weather/daily_weather.csv` |
| Sentinel NDVI | `{field}/satellite/sentinel/manifest.json` → per-scene `*_ndvi.tif` |
| Field boundary | `{field}/boundary/field_boundary.geojson` |
| CDL crop-year | `{field}/derived/tables/ndvi_year_crop_join.csv` |

## Architecture

- **`scripts/field_season_dashboard.py`** — standalone CLI script that loads data, calculates metrics, detects events, and renders the dashboard.
- Uses **matplotlib** with a shared date axis across all panels, consistent with existing reporting scripts.
- Functions are modular so the script can be imported for programmatic reuse.

## Prerequisites

- Python 3.9+
- pandas, numpy, matplotlib, geopandas, rasterio
- Data-pipeline runtime installed at `~/my-farm-advisor-runtime/data-pipeline`

## Quick start

```bash
cd ~/my-farm-advisor-runtime/data-pipeline/src
python ~/my-farm-advisor-skills/my-farm-advisor/eda/field-season-dashboard/scripts/field_season_dashboard.py \
  --grower ia-grower \
  --farm ia-grower-iowa \
  --field osm-1360326425 \
  --year 2025
```

Output: `growers/ia-grower/farms/ia-grower-iowa/fields/osm-1360326425/derived/reports/field_season_dashboard_2025.png`

## Documentation

- [Workflow Guide](GUIDE.md) — detailed commands, parameters, and design decisions.
- [AGENTS.md](AGENTS.md) — local agent instructions.
