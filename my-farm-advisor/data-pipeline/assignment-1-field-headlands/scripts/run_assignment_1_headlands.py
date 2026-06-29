#!/usr/bin/env python3
"""Discover growers in the data pipeline runtime and generate headlands ring GeoPackages.

Reads each field's field_boundary.geojson, validates CRS, computes a 21 m headlands
buffer ring in UTM (per-field zone), and writes three files per field:

    growers/{grower}/farms/{farm}/fields/{field-id}/derived/headlands/field_boundary.gpkg
    growers/{grower}/farms/{farm}/fields/{field-id}/derived/headlands/headlands_ring.gpkg
    growers/{grower}/farms/{farm}/fields/{field-id}/derived/headlands/headlands_validation.png

Usage
-----
export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
python scripts/run_assignment_1_headlands.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure the subskill src package is importable
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE / "src"))

from field_headlands import process_single_field  # noqa: E402


def discover_fields(data_root: Path) -> list[Path]:
    """Return a list of field-level field_boundary.geojson paths in the runtime."""
    growers_dir = data_root / "growers"
    if not growers_dir.is_dir():
        raise FileNotFoundError(f"Growers directory not found: {growers_dir}")

    boundary_files = []
    for grower_dir in sorted(growers_dir.iterdir()):
        farms_dir = grower_dir / "farms"
        if not farms_dir.is_dir():
            continue
        for farm_dir in sorted(farms_dir.iterdir()):
            fields_dir = farm_dir / "fields"
            if not fields_dir.is_dir():
                continue
            for field_dir in sorted(fields_dir.iterdir()):
                boundary = field_dir / "boundary" / "field_boundary.geojson"
                if boundary.is_file():
                    boundary_files.append(boundary)
    return boundary_files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate headlands ring GeoPackages for all fields in the runtime."
    )
    parser.add_argument(
        "--data-root",
        default=os.environ.get("DATA_PIPELINE_DATA_ROOT"),
        help="Path to the data pipeline runtime root (default: $DATA_PIPELINE_DATA_ROOT)",
    )
    parser.add_argument(
        "--buffer-m",
        type=float,
        default=21.0,
        help="Headlands buffer width in meters (default: 21.0)",
    )
    args = parser.parse_args()

    if args.data_root is None:
        parser.error(
            "DATA_PIPELINE_DATA_ROOT is not set. "
            "Provide --data-root or export DATA_PIPELINE_DATA_ROOT."
        )

    data_root = Path(args.data_root).resolve()
    pipeline_root = data_root / "data-pipeline"

    print(f"Data pipeline root: {pipeline_root}")

    boundary_files = discover_fields(pipeline_root)
    if not boundary_files:
        print("No field boundary files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(boundary_files)} field(s) with boundaries")

    for bf in boundary_files:
        field_name = bf.parent.parent.name
        farm_name = bf.parent.parent.parent.parent.name
        grower_name = bf.parent.parent.parent.parent.parent.parent.name
        output_dir = bf.parent.parent / "derived" / "headlands"

        print(f"\n  Grower: {grower_name}  Farm: {farm_name}  Field: {field_name}")
        print(f"  Boundary: {bf}")
        print(f"  Output:   {output_dir}")

        try:
            fb_path, hr_path, png_path = process_single_field(
                geojson_path=bf,
                output_dir=output_dir,
                buffer_m=args.buffer_m,
            )
            print(f"  ✓ field_boundary    → {fb_path}")
            print(f"  ✓ headlands_ring    → {hr_path}")
            print(f"  ✓ validation plot   → {png_path}")
        except Exception as exc:
            print(f"  ✗ ERROR: {exc}", file=sys.stderr)

    print("\nDone.")


if __name__ == "__main__":
    main()
