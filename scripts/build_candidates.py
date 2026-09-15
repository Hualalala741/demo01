from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask, shapes
from shapely.geometry import shape

from gover_mvp.candidates import build_abandonment_mask


AREA_CRS = "EPSG:32650"  # 永春县所在UTM 50N，用于面积计算


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从土地覆盖变化生成疑似撂荒候选地。")
    parser.add_argument("--historical", type=Path, required=True, help="历史土地覆盖GeoTIFF")
    parser.add_argument("--recent", type=Path, nargs="+", required=True, help="至少一个近年土地覆盖GeoTIFF")
    parser.add_argument("--protected", type=Path, help="自然保护区矢量，可选")
    parser.add_argument("--output", type=Path, required=True, help="输出GeoPackage")
    parser.add_argument("--historical-crop-values", type=int, nargs="+", default=[5])
    parser.add_argument("--recent-proxy-values", type=int, nargs="+", default=[8, 11])
    parser.add_argument("--minimum-patch-mu", type=float, default=5.0, help="预处理时移除的小斑块面积")
    return parser.parse_args()


def read_aligned(path: Path, reference: rasterio.DatasetReader) -> np.ndarray:
    with rasterio.open(path) as source:
        if (
            source.crs != reference.crs
            or source.transform != reference.transform
            or source.width != reference.width
            or source.height != reference.height
        ):
            raise ValueError(f"栅格未对齐：{path}")
        return source.read(1)


def subtract_protected(
    candidate_mask: np.ndarray,
    protected_path: Path | None,
    crs,
    transform,
) -> np.ndarray:
    if protected_path is None:
        return candidate_mask
    protected = gpd.read_file(protected_path).to_crs(crs)
    if protected.empty:
        return candidate_mask
    protected_mask = geometry_mask(
        protected.geometry,
        out_shape=candidate_mask.shape,
        transform=transform,
        invert=True,
    )
    return candidate_mask & ~protected_mask


def vectorize(
    mask: np.ndarray,
    transform,
    crs,
    minimum_patch_mu: float,
    protection_screened: bool,
) -> gpd.GeoDataFrame:
    geometries = [
        shape(geometry)
        for geometry, value in shapes(mask.astype("uint8"), mask=mask, transform=transform)
        if value == 1
    ]
    if not geometries:
        return gpd.GeoDataFrame(columns=["land_id", "geometry"], geometry="geometry", crs=crs)

    lands = gpd.GeoDataFrame({"geometry": geometries}, crs=crs).to_crs(AREA_CRS)
    lands["area_mu"] = lands.area / 666.6666667
    lands = lands.loc[lands["area_mu"] >= minimum_patch_mu].copy().reset_index(drop=True)
    lands["land_id"] = [f"YC-LAND-{index:05d}" for index in range(1, len(lands) + 1)]
    lands["historical_class"] = "crops"
    lands["current_class"] = "rangeland/bare"
    lands["abandoned_confidence"] = 0.65
    lands["protected_overlap"] = False if protection_screened else "unknown"
    lands["protection_screened"] = protection_screened
    lands["climate_pass"] = "unknown"
    lands["soil_pass"] = "unknown"
    lands["irrigation_available"] = "unknown"
    for column in ("cost_score", "market_score", "risk_score", "policy_score"):
        lands[column] = 50.0
    lands["data_completeness"] = 0.45
    return lands.to_crs("EPSG:4326")


def main() -> None:
    args = parse_args()
    with rasterio.open(args.historical) as historical_source:
        historical = historical_source.read(1)
        valid = historical_source.dataset_mask().astype(bool)
        recent_layers = [read_aligned(path, historical_source) for path in args.recent]
        candidate_mask = build_abandonment_mask(
            historical,
            recent_layers,
            valid,
            args.historical_crop_values,
            args.recent_proxy_values,
        )
        candidate_mask = subtract_protected(
            candidate_mask,
            args.protected,
            historical_source.crs,
            historical_source.transform,
        )
        lands = vectorize(
            candidate_mask,
            historical_source.transform,
            historical_source.crs,
            args.minimum_patch_mu,
            protection_screened=args.protected is not None,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()
    lands.to_file(args.output, layer="candidate_lands", driver="GPKG")
    print(f"已生成 {len(lands)} 块候选土地：{args.output}")


if __name__ == "__main__":
    main()
