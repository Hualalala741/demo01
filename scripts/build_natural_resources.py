from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape

from gover_mvp.candidates import build_stable_natural_resource_mask


AREA_CRS = "EPSG:32650"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成稳定裸地/草灌地潜在自然资源斑块。")
    parser.add_argument("--annual", type=Path, nargs="+", required=True, help="已对齐的年度土地覆盖GeoTIFF")
    parser.add_argument("--output", type=Path, required=True, help="输出GeoPackage")
    parser.add_argument("--resource-values", type=int, nargs="+", default=[8, 11])
    parser.add_argument("--minimum-patch-mu", type=float, default=20.0)
    parser.add_argument("--maximum-patch-mu", type=float, default=500.0)
    return parser.parse_args()


def build_resources(
    annual_paths: list[Path],
    resource_values: list[int],
    minimum_patch_mu: float,
    maximum_patch_mu: float,
) -> gpd.GeoDataFrame:
    with rasterio.open(annual_paths[0]) as reference:
        annual_layers = [reference.read(1)]
        valid = reference.dataset_mask().astype(bool)
        transform = reference.transform
        crs = reference.crs
        for path in annual_paths[1:]:
            with rasterio.open(path) as source:
                if (
                    source.crs != crs
                    or source.transform != transform
                    or source.width != reference.width
                    or source.height != reference.height
                ):
                    raise ValueError(f"栅格未对齐：{path}")
                annual_layers.append(source.read(1))

    resource_mask = build_stable_natural_resource_mask(annual_layers, valid, resource_values)
    geometries = [
        shape(geometry)
        for geometry, value in shapes(
            resource_mask.astype("uint8"),
            mask=resource_mask,
            transform=transform,
        )
        if value == 1
    ]
    resources = gpd.GeoDataFrame({"geometry": geometries}, crs=crs).to_crs(AREA_CRS)
    resources["area_mu"] = resources.area / 666.6666667
    resources = resources.loc[
        resources["area_mu"].between(minimum_patch_mu, maximum_patch_mu, inclusive="both")
    ].copy()
    resources = resources.sort_values("area_mu", ascending=False).reset_index(drop=True)
    resources["land_id"] = [f"YC-NR-{index:05d}" for index in range(1, len(resources) + 1)]
    resources["resource_type"] = "stable_bare_or_rangeland"
    resources["historical_class"] = "bare/rangeland"
    resources["current_class"] = "bare/rangeland"
    resources["resource_stability_years"] = len(annual_layers)
    resources["protected_overlap"] = "unknown"
    resources["protection_screened"] = False
    resources["climate_pass"] = "unknown"
    resources["soil_pass"] = "unknown"
    resources["irrigation_available"] = "unknown"
    for column in ("cost_score", "market_score", "risk_score", "policy_score"):
        resources[column] = 50.0
    resources["data_completeness"] = 0.35
    return resources.to_crs("EPSG:4326")


def main() -> None:
    args = parse_args()
    resources = build_resources(
        args.annual,
        args.resource_values,
        args.minimum_patch_mu,
        args.maximum_patch_mu,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()
    resources.to_file(args.output, layer="candidate_lands", driver="GPKG")
    print(
        f"已生成 {len(resources)} 块稳定裸地/草灌地潜在资源：{args.output}；"
        f"面积范围 {args.minimum_patch_mu:g}—{args.maximum_patch_mu:g} 亩"
    )


if __name__ == "__main__":
    main()
