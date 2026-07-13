# Field Portfolio EDA

## Overview

This subskill evaluates a three-grower land portfolio through three analytical dimensions:

1. **Field Boundaries** — physical geometry risk (size, shape, regularity)
2. **Weather** — environmental volatility (precipitation, temperature, GDD)
3. **CDL / Cropland Data Layer** — strategic planting decisions (diversity, rotation, transitions)

## Dataset

- **30 fields** (10 per grower)
- **Illinois** — Iroquois County
- **Iowa** — Kossuth County
- **Nebraska** — York County
- **Timespan** — 2021–2025 for weather and CDL

## Key Insight

- **Iowa** = disciplined, low-volatility asset (strict rotation, consistent scale)
- **Illinois** = highest-risk holding (extreme size variability, mixed cropping)
- **Nebraska** = small-scale, regular geometry, irrigation-supported flexibility

## Artifacts

| Module | Outputs |
|--------|---------|
| Boundaries | violin plot, circularity bar chart, std-dev CSV, composite + individual maps |
| Weather | spring precip time-series, temp heatmap, GDD CSV, precip map |
| CDL | diversity line graph, rotation frequency chart, transition matrix CSV, crop map |
| Report | self-contained HTML with embedded images |

## Scripts

| Script | Module |
|--------|--------|
| `scripts/eda_field_portfolio_boundaries.py` | Field geometry analysis |
| `scripts/eda_field_portfolio_weather.py` | Weather & climate analysis |
| `scripts/eda_field_portfolio_cdl.py` | Cropland Data Layer analysis |
| `scripts/eda_field_portfolio_report.py` | Static HTML report assembly |

## Runtime

All scripts read from and write to the canonical data pipeline runtime under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/`.

## License

Apache-2.0
