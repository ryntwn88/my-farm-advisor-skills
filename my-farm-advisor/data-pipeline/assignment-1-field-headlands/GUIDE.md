---
name: assignment-1-field-headlands
description: >
  Compute a 21 m headlands buffer ring from individual field boundaries in the
  My Farm Advisor data pipeline. Validates CRS, projects each field to its own
  UTM zone, calculates area metrics, and writes field_boundary, headlands_ring,
  and a validation PNG per field.
version: 1.0.0
author: Clayton Young / Superior Byte Works, LLC
tags: [geospatial, headlands, field-operations, buffer, data-pipeline]
---

# Workflow: assignment-1-field-headlands

## Description

Read each **individual field's** `field_boundary.geojson` from the data pipeline runtime, validate the CRS is **EPSG:4326**, copy to a UTM-projected working GeoDataFrame (using the **per-field UTM zone**), compute field and headlands area metrics, create a **21 m** negative inner buffer, derive the headlands ring by differencing, convert only the ring back to EPSG:4326, and write three files per field:

- `field_boundary.gpkg` — full field boundary (EPSG:4326) with `area_meters_squared` and `area_acres` columns
- `headlands_ring.gpkg` — headlands ring (EPSG:4326) with `headlands_area_meters_squared` and `headlands_area_acres` columns
- `headlands_validation.png` — visual validation map showing boundary outline (dark green) and headlands ring (orange fill) with area annotations

## When to Use This Workflow

- **Headlands exclusion**: Exclude edge effects from agronomic or remote-sensing analysis
- **Operational analysis**: Quantify headlands acres and the share of a field devoted to turning or overlap zones
- **Per-field processing**: When farm-level aggregation fails because fields are too spread out for a single UTM zone

## Quick Start

```bash
export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline/assignment-1-field-headlands

"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/run_assignment_1_headlands.py
```

## Pipeline Steps

1. **Read & Validate** — Load `field_boundary.geojson` and confirm CRS is EPSG:4326
2. **UTM Projection (per field)** — Compute UTM zone from the single field's centroid, project working copy
3. **Field Area** — Calculate `area_meters_squared` and `area_acres`; write back to original_gdf
4. **Inner Buffer** — Create a negative 21 m buffer on the UTM working copy
5. **Headlands Ring** — Difference of full boundary and inner buffer
6. **Headlands Area** — Calculate headlands ring area in sqm and acres
7. **Reproject Ring** — Convert only the headlands ring back to EPSG:4326
8. **Write Outputs** — Three files per field under `fields/{field-id}/derived/headlands/`

## Output Files

| File | CRS | Contents |
|------|-----|----------|
| `derived/headlands/field_boundary.gpkg` | EPSG:4326 | Original boundary + area columns |
| `derived/headlands/headlands_ring.gpkg` | EPSG:4326 | Headlands ring + area columns |
| `derived/headlands/headlands_validation.png` | — | Validation map (boundary + ring) |

## Dependencies

- `geopandas` (available in the runtime venv)
- `matplotlib`
- `numpy`

## Python API Reference

### `read_field_boundaries(geojson_path)`

Read a GeoJSON file and validate its CRS is EPSG:4326.

### `calculate_utm_epsg(gdf)`

Return the appropriate UTM EPSG code (northern or southern) from the GeoDataFrame centroid.

### `plot_headlands_validation(field_gdf, ring_gdf, output_path, title=None)`

Render a validation map of the field boundary and headlands ring, save as PNG.

### `process_single_field(geojson_path, output_dir, buffer_m=21.0)`

Run the full headlands buffer pipeline on a single field. Returns `(field_boundary_path, headlands_ring_path, validation_png_path)`.
