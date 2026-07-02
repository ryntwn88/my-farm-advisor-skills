#!/usr/bin/env python3
"""
eda_field_portfolio_report.py — Static HTML report generator

Assembles the complete Assignment 2 "Operational Stability and Risk" EDA
into a single self-contained HTML file with embedded images.

Usage:
    python scripts/eda/eda_field_portfolio_report.py
"""

from __future__ import annotations

import base64
from pathlib import Path

import pandas as pd

RUNTIME_ROOT = Path("/home/coder/my-farm-advisor-runtime/data-pipeline")
INPUT_DIR = RUNTIME_ROOT / "eda" / "field-portfolio"
OUTPUT_DIR = INPUT_DIR / "report"


def _img_b64(path: Path) -> str:
    with path.open("rb") as f:
        data = f.read()
    return base64.b64encode(data).decode("ascii")


def _csv_to_html(path: Path) -> str:
    df = pd.read_csv(path)
    return df.to_html(index=False, classes="data-table", border=0)


def _build_html() -> str:
    # Load all image assets
    b = INPUT_DIR / "boundaries"
    w = INPUT_DIR / "weather"
    c = INPUT_DIR / "cdl"

    img = {
        "violin": _img_b64(b / "boundaries_field_size_violin.png"),
        "circ_bar": _img_b64(b / "boundaries_circularity_index_bar.png"),
        "circ_map": _img_b64(b / "boundaries_circularity_map.png"),
        "precip_ts": _img_b64(w / "weather_spring_precip_variance_timeseries.png"),
        "temp_heatmap": _img_b64(w / "weather_monthly_temp_heatmap.png"),
        "precip_map": _img_b64(w / "weather_precip_map.png"),
        "div_line": _img_b64(c / "cdl_diversity_score_line.png"),
        "rot_freq": _img_b64(c / "cdl_rotation_frequency.png"),
        "crop_map": _img_b64(c / "cdl_dominant_crop_map.png"),
    }

    # CSV tables
    table_size = _csv_to_html(b / "boundaries_size_stddev_comparison.csv")
    table_gdd = _csv_to_html(w / "weather_ne_gdd_comparison.csv")
    table_trans = _csv_to_html(c / "cdl_iowa_transition_matrix.csv")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Operational Stability and Risk — Field Portfolio EDA Report</title>
<style>
  body {{
    font-family: Georgia, serif;
    line-height: 1.7;
    color: #222;
    max-width: 900px;
    margin: 0 auto;
    padding: 30px 20px;
    background: #fafafa;
  }}
  h1 {{
    font-size: 1.9rem;
    color: #1a1a1a;
    border-bottom: 3px solid #2E86AB;
    padding-bottom: 10px;
    margin-bottom: 5px;
  }}
  .subtitle {{
    font-size: 0.95rem;
    color: #555;
    margin-bottom: 30px;
  }}
  h2 {{
    font-size: 1.4rem;
    color: #1a1a1a;
    margin-top: 40px;
    border-left: 5px solid #2E86AB;
    padding-left: 12px;
  }}
  h3 {{
    font-size: 1.15rem;
    color: #333;
    margin-top: 25px;
  }}
  .artifact {{
    margin: 20px 0;
    text-align: center;
  }}
  .artifact img {{
    max-width: 100%;
    height: auto;
    border: 1px solid #ddd;
    border-radius: 4px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.08);
  }}
  .caption {{
    font-size: 0.85rem;
    color: #666;
    margin-top: 6px;
    font-style: italic;
  }}
  table.data-table {{
    border-collapse: collapse;
    width: 100%;
    margin: 15px 0;
    font-size: 0.9rem;
    font-family: "Segoe UI", sans-serif;
  }}
  table.data-table th {{
    background: #2E86AB;
    color: white;
    padding: 8px 10px;
    text-align: left;
  }}
  table.data-table td {{
    padding: 6px 10px;
    border-bottom: 1px solid #e0e0e0;
  }}
  table.data-table tr:nth-child(even) {{
    background: #f4f4f4;
  }}
  .key-finding {{
    background: #eef6fc;
    border-left: 4px solid #2E86AB;
    padding: 12px 16px;
    margin: 15px 0;
    border-radius: 3px;
  }}
  .transition {{
    font-style: italic;
    color: #444;
    margin: 20px 0;
    padding: 10px 14px;
    background: #f9f9f9;
    border-radius: 4px;
  }}
  ul {{
    margin-top: 8px;
  }}
  li {{
    margin-bottom: 6px;
  }}
</style>
</head>
<body>

<h1>Operational Stability and Risk</h1>
<p class="subtitle">
  A Field Portfolio Analysis Across Illinois, Iowa, and Nebraska &middot;
  Assignment 2 EDA Report &middot; 2026
</p>

<h2>Executive Summary</h2>
<p>
  This exploratory data analysis evaluates three farms as a land portfolio,
  examining how <strong>physical geometry</strong>, <strong>environmental volatility</strong>, and
  <strong>strategic planting decisions</strong> interact to shape operational risk. The dataset
  comprises 30 fields (10 per grower) in Iroquois County (IL), Kossuth County (IA), and
  York County (NE), spanning 2021–2025 for weather and crop data.
</p>

<div class="key-finding">
  <strong>Key Findings:</strong>
  <ul>
    <li><strong>Illinois</strong> shows the highest field-size variability (CV = 1.33), suggesting
    the most heterogeneous operational landscape and highest machinery-efficiency risk.</li>
    <li><strong>Iowa</strong> enforces a strict Corn–Soy rotation (Soybeans → Corn 100% of transitions),
    indicating disciplined, low-diversity risk management.</li>
    <li><strong>Nebraska</strong> fields are smallest and most regular in shape, with mixed
    crop strategies that may reflect center-pivot irrigation flexibility.</li>
  </ul>
</div>

<!-- ===================================================================== -->
<h2>1. Field Boundaries — Physical Geometry Risk</h2>
<p>
  Field size and shape are the foundational constraints on any operation.
  Large, irregular fields increase input waste, complicate machinery routing,
  and raise labor costs. In this section we quantify those risks across the portfolio.
</p>

<h3>1.1 Field Size Distribution</h3>
<div class="artifact">
  <img src="data:image/png;base64,{img['violin']}" alt="Field size violin plot">
  <p class="caption">
    Violin plot of field sizes by grower. Iowa fields are largest on average (~116 ac),
    while Illinois spans the widest range (3–213 ac).
  </p>
</div>

<h3>1.2 Shape Regularity (Circularity Index)</h3>
<div class="artifact">
  <img src="data:image/png;base64,{img['circ_bar']}" alt="Circularity index bar chart">
  <p class="caption">
    Circularity Index (4πA / P²) for all 30 fields. Values near 1.0 indicate
    regular, machinery-friendly shapes; lower values signal irregular or elongated parcels.
  </p>
</div>

<h3>1.3 Size Variability Comparison</h3>
{table_size}

<h3>1.4 Geospatial View</h3>
<div class="artifact">
  <img src="data:image/png;base64,{img['circ_map']}" alt="Circularity map">
  <p class="caption">
    Composite map of all 30 fields colored by Circularity Index. Greener polygons
    are more regular; yellower/redder ones are more irregular.
  </p>
</div>

<div class="transition">
  <strong>→ Leading into Weather:</strong> Size and shape tell us <em>how</em> we farm;
  weather tells us <em>what</em> we face. The next section examines the environmental
  volatility that these fields experience.
</div>

<!-- ===================================================================== -->
<h2>2. Weather — Environmental Volatility</h2>
<p>
  Weather is the largest uncontrollable risk in agriculture. Spring precipitation
  determines planting windows and germination success; heat accumulation drives
  maturity timing. We analyze both temporal variance and spatial patterns.
</p>

<h3>2.1 Spring Precipitation Variance (Apr–May)</h3>
<div class="artifact">
  <img src="data:image/png;base64,{img['precip_ts']}" alt="Spring precipitation time series">
  <p class="caption">
    One representative field per grower. Spring precipitation varies substantially
    year-to-year, with no clear trend but notable inter-annual swings that affect
    planting risk across all three states.
  </p>
</div>

<h3>2.2 Monthly Temperature Heatmap</h3>
<div class="artifact">
  <img src="data:image/png;base64,{img['temp_heatmap']}" alt="Temperature heatmap">
  <p class="caption">
    Average monthly temperature (°C) across the three growers. Nebraska shows the
    warmest summers, while Illinois and Iowa track closely, reflecting their similar
    latitudes.
  </p>
</div>

<h3>2.3 Growing Degree Days (Nebraska, 2025)</h3>
{table_gdd}

<h3>2.4 Cumulative Precipitation Map (2025)</h3>
<div class="artifact">
  <img src="data:image/png;base64,{img['precip_map']}" alt="Precipitation map">
  <p class="caption">
    Fields colored by total 2025 precipitation. Darker blue indicates wetter conditions,
    which may delay planting or increase disease pressure.
  </p>
</div>

<div class="transition">
  <strong>→ Leading into CDL:</strong> Knowing the environment, what do growers
  <em>choose</em> to plant? The next section examines strategic crop decisions
  through the USDA Cropland Data Layer.
</div>

<!-- ===================================================================== -->
<h2>3. CDL / Cropland Data Layer — Strategic Planting Decisions</h2>
<p>
  Crop choice is the primary lever growers pull to manage risk. Rotation patterns
  reveal risk tolerance, soil-health priorities, and market strategy. We analyze
  diversity, rotation discipline, and transition probabilities.
</p>

<h3>3.1 Crop Diversity Over Time</h3>
<div class="artifact">
  <img src="data:image/png;base64,{img['div_line']}" alt="Diversity score line graph">
  <p class="caption">
    Shannon Diversity Index by grower, 2021–2025. Higher values indicate more
    mixed cropping; lower values suggest monoculture or strict two-crop rotation.
  </p>
</div>

<h3>3.2 Rotation Pattern Frequency</h3>
<div class="artifact">
  <img src="data:image/png;base64,{img['rot_freq']}" alt="Rotation frequency chart">
  <p class="caption">
    Stacked bar chart of rotation classifications. Iowa leans heavily into
    Corn–Soy rotation, while Illinois and Nebraska show more continuous-corn fields.
  </p>
</div>

<h3>3.3 Iowa Transition Probability Matrix</h3>
{table_trans}
<p>
  The matrix reveals that Iowa fields in <strong>Soybeans</strong> always transition
  to <strong>Corn</strong> (100%). Fields in <strong>Corn</strong> switch to Soybeans
  56% of the time, with the remainder staying in Corn—suggesting a strict but
  occasionally broken two-year rotation.
</p>

<h3>3.4 Dominant Crop Map (2025)</h3>
<div class="artifact">
  <img src="data:image/png;base64,{img['crop_map']}" alt="Dominant crop map">
  <p class="caption">
    Composite map of all 30 fields colored by their 2025 dominant CDL crop.
    Yellow = Corn, Blue = Soybeans, Green = Grass/Pasture.
  </p>
</div>

<!-- ===================================================================== -->
<h2>4. Conclusion & Next Steps</h2>

<div class="key-finding">
  <strong>Portfolio Character:</strong>
  <ul>
    <li><strong>Iowa</strong> presents the most <em>disciplined</em> risk profile:
    consistent scale, strict rotation, and moderate weather variability.
    It behaves like a low-volatility asset in the portfolio.</li>
    <li><strong>Illinois</strong> is the <em>highest-risk</em> holding: extreme
    size heterogeneity, diverse cropping, and no clear rotation lock-in.
    It offers potential upside but requires active management.</li>
    <li><strong>Nebraska</strong> is the <em>smallest-scale, most-regular</em>
    set, with mixed crop strategies likely supported by center-pivot irrigation.
    Its weather-driven GDD spread hints at microclimate sensitivity.</li>
  </ul>
</div>

<h3>Suggested Further Exploration</h3>
<ul>
  <li><strong>NDVI validation:</strong> Overlay satellite-derived vegetation indices
  to test whether weather volatility in 2021–2025 actually impacted crop health.</li>
  <li><strong>Yield correlation:</strong> If yield data becomes available, test whether
  Iowa's rotation discipline correlates with productivity stability.</li>
  <li><strong>GDD–precipitation modeling:</strong> Build an interaction model to
  optimize planting-date recommendations given spring moisture and heat accumulation.</li>
  <li><strong>Irrigation analysis:</strong> For Nebraska, separate irrigated from
  rainfed fields (via shape or additional data) to quantify irrigation's risk-mitigation effect.</li>
</ul>

<p style="margin-top:40px; font-size:0.85rem; color:#777; border-top:1px solid #ddd; padding-top:10px;">
  Report generated by <code>eda_field_portfolio_report.py</code> &middot;
  Part of the My Farm Advisor <code>eda-field-portfolio</code> subskill.
</p>

</body>
</html>
"""
    return html


def main() -> None:
    print("=" * 60)
    print("Generating static HTML report")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    html = _build_html()
    out_path = OUTPUT_DIR / "assignment_2_eda_report.html"
    out_path.write_text(html, encoding="utf-8")

    size_kb = len(html) / 1024
    print(f"\n  ✓ {out_path.name}")
    print(f"    Size: {size_kb:.1f} KB")
    print(f"\n{'=' * 60}")


if __name__ == "__main__":
    main()
