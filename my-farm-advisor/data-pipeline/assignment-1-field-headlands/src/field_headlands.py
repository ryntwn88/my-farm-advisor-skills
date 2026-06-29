from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np

ACRES_PER_SQM = 0.0002471053814671653


def read_field_boundaries(geojson_path: str | Path) -> gpd.GeoDataFrame:
    """Read field boundary GeoJSON and validate CRS is EPSG:4326."""
    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None:
        raise ValueError(f"{geojson_path} has no CRS")
    epsg = gdf.crs.to_epsg()
    if epsg != 4326:
        raise ValueError(f"Expected EPSG:4326, got EPSG:{epsg} from {geojson_path}")
    return gdf


def calculate_utm_epsg(gdf: gpd.GeoDataFrame) -> int:
    """Determine the appropriate UTM EPSG code from the GeoDataFrame centroid."""
    centroid = gdf.geometry.unary_union.centroid
    lon = centroid.x
    zone = int(np.floor((lon + 180) / 6)) + 1
    if centroid.y >= 0:
        return 32600 + zone
    else:
        return 32700 + zone


def plot_headlands_validation(
    field_gdf: gpd.GeoDataFrame,
    ring_gdf: gpd.GeoDataFrame,
    output_path: str | Path,
    title: str | None = None,
) -> Path:
    """Render a validation map of the field boundary and headlands ring.

    Parameters
    ----------
    field_gdf : gpd.GeoDataFrame
        Original field boundary in EPSG:4326 (with area_acres).
    ring_gdf : gpd.GeoDataFrame
        Headlands ring in EPSG:4326 (with headlands_area_acres).
    output_path : str | Path
        Where to save the PNG.
    title : str | None
        Optional plot title.

    Returns
    -------
    Path to the saved PNG.
    """
    fig, ax = plt.subplots(figsize=(10, 10))

    field_gdf.boundary.plot(ax=ax, color="darkgreen", linewidth=2, label="Field boundary")
    ring_gdf.plot(ax=ax, color="#fdba74", alpha=0.7, edgecolor="#c2410c", linewidth=1, label="Headlands ring")

    # Annotate with metrics
    for idx in range(len(field_gdf)):
        row = field_gdf.iloc[idx]
        centroid = row.geometry.centroid
        field_area = row.get("area_acres", 0.0)
        hl_area = ring_gdf.iloc[idx].get("headlands_area_acres", 0.0) if idx < len(ring_gdf) else 0.0
        annotation = f"{field_area:.1f} ac\nhl: {hl_area:.1f} ac"
        ax.annotate(
            annotation,
            (centroid.x, centroid.y),
            fontsize=8,
            ha="center",
            color="darkgreen",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.85, edgecolor="darkgreen"),
        )

    if title is None:
        title = "Field Boundary & 21 m Headlands Ring"
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_axis_off()
    ax.legend(loc="lower right")
    plt.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return output_path


def process_single_field(
    geojson_path: str | Path,
    output_dir: str | Path,
    buffer_m: float = 21.0,
) -> tuple[Path, Path, Path]:
    """Run the full headlands buffer pipeline on a single field boundary GeoJSON.

    Steps
    -----
    1. Read and validate CRS is EPSG:4326.
    2. Project to UTM (zone determined from this single field's centroid).
    3. Compute field boundary area (sqm + acres), store on original_gdf.
    4. Create negative inner buffer.
    5. Difference full boundary minus inner buffer → headlands ring.
    6. Compute headlands ring area (sqm + acres).
    7. Convert only headlands ring back to EPSG:4326.
    8. Write field_boundary.gpkg, headlands_ring.gpkg, and validation PNG.

    Returns
    -------
    (field_boundary_path, headlands_ring_path, validation_png_path)
    """
    geojson_path = Path(geojson_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Read & validate
    original_gdf = read_field_boundaries(geojson_path)

    # 2. Project to UTM (per-field zone)
    utm_epsg = calculate_utm_epsg(original_gdf)
    working_gdf = original_gdf.to_crs(epsg=utm_epsg)

    # 3. Compute field boundary area
    working_gdf["area_meters_squared"] = working_gdf.geometry.area
    working_gdf["area_acres"] = working_gdf["area_meters_squared"] * ACRES_PER_SQM

    original_gdf["area_meters_squared"] = working_gdf["area_meters_squared"].values
    original_gdf["area_acres"] = working_gdf["area_acres"].values

    # 4–5. Create inner buffer & derive headlands ring
    rings = []
    ring_ids = []
    for idx, geom in working_gdf.geometry.items():
        inner = geom.buffer(-buffer_m)
        ring_geom = geom if inner.is_empty else geom.difference(inner)
        if not ring_geom.is_empty:
            rings.append(ring_geom)
            ring_ids.append(idx)

    if not rings:
        raise ValueError("No headlands ring was generated — field may be smaller than the buffer width")

    # Build headlands GeoDataFrame preserving field attributes
    headlands_gdf = working_gdf.loc[ring_ids].copy()
    headlands_gdf = headlands_gdf.set_geometry(
        gpd.GeoSeries(rings, crs=working_gdf.crs)
    )

    # 6. Compute headlands ring area
    headlands_gdf["headlands_area_meters_squared"] = headlands_gdf.geometry.area
    headlands_gdf["headlands_area_acres"] = headlands_gdf["headlands_area_meters_squared"] * ACRES_PER_SQM

    # 7. Convert only headlands ring back to EPSG:4326
    headlands_gdf = headlands_gdf.to_crs(epsg=4326)

    # 8. Write outputs
    field_boundary_path = output_dir / "field_boundary.gpkg"
    headlands_ring_path = output_dir / "headlands_ring.gpkg"
    validation_png_path = output_dir / "headlands_validation.png"

    original_gdf.to_file(field_boundary_path, layer="field_boundary", driver="GPKG")
    headlands_gdf.to_file(headlands_ring_path, layer="headlands_ring", driver="GPKG")

    field_id = original_gdf.iloc[0].get("field_id", geojson_path.stem)
    plot_headlands_validation(
        field_gdf=original_gdf,
        ring_gdf=headlands_gdf,
        output_path=validation_png_path,
        title=f"{field_id} — Field Boundary & 21 m Headlands Ring",
    )

    return field_boundary_path, headlands_ring_path, validation_png_path
