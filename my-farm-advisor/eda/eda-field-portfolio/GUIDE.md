---
name: eda-field-portfolio-guide
description: Complete workflow guide for the Field Portfolio EDA subskill. Covers boundaries, weather, and CDL analysis with copy-paste commands.
version: 1.0.0
---

# Field Portfolio EDA — Workflow Guide

## Narrative Arc

> **Boundaries** set the physical constraints → **Weather** introduces environmental volatility → **CDL** reveals how growers strategically respond. Together, they paint a risk portrait of the portfolio.

## Prerequisites

```bash
# Ensure the data pipeline runtime is installed and the dataset is built
export DATA_PIPELINE_DATA_ROOT="/home/coder/my-farm-advisor-runtime/data-pipeline"
export DATA_PIPELINE_INSTALL_SCRIPT="/path/to/install.sh"
```

## Step-by-Step

### 1. Field Boundaries

```bash
cd ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src
python scripts/eda/eda_field_portfolio_boundaries.py
```

Outputs:
- `eda/field-portfolio/boundaries/boundaries_field_size_violin.png`
- `eda/field-portfolio/boundaries/boundaries_circularity_index_bar.png`
- `eda/field-portfolio/boundaries/boundaries_size_stddev_comparison.csv`
- `eda/field-portfolio/boundaries/boundaries_circularity_map.png`
- `eda/field-portfolio/boundaries/boundaries_circularity_map_{il,ia,ne}.png`

### 2. Weather

```bash
cd ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src
python scripts/eda/eda_field_portfolio_weather.py
```

Outputs:
- `eda/field-portfolio/weather/weather_spring_precip_variance_timeseries.png`
- `eda/field-portfolio/weather/weather_monthly_temp_heatmap.png`
- `eda/field-portfolio/weather/weather_ne_gdd_comparison.csv`
- `eda/field-portfolio/weather/weather_precip_map.png`

### 3. CDL / Cropland Data Layer

```bash
cd ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src
python scripts/eda/eda_field_portfolio_cdl.py
```

Outputs:
- `eda/field-portfolio/cdl/cdl_diversity_score_line.png`
- `eda/field-portfolio/cdl/cdl_rotation_frequency.png`
- `eda/field-portfolio/cdl/cdl_iowa_transition_matrix.csv`
- `eda/field-portfolio/cdl/cdl_dominant_crop_map.png`

### 4. Report Assembly

```bash
cd ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src
python scripts/eda/eda_field_portfolio_report.py
```

Output:
- `eda/field-portfolio/report/assignment_2_eda_report.html`

Open the HTML in any browser — it is self-contained with all images embedded.

## Design Decisions

- **Static outputs only** — no interactive dashboard
- **Self-contained HTML** — base64-encoded images for portability
- **Tight-cropped maps** — each grower panel zoomed to field extent
- **Vertical colorbars** — placed on the right edge to avoid overlapping map panels
- **No soil analysis** — excluded per assignment requirements
