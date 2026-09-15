from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import planetary_computer
import rasterio
from pystac_client import Client
from rasterio.mask import mask
from shapely.geometry import mapping


STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "io-lulc-annual-v02"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="下载并裁剪永春县年度10米土地覆盖数据。")
    parser.add_argument("--boundary", type=Path, required=True, help="永春县边界文件")
    parser.add_argument("--years", type=int, nargs="+", default=[2017, 2022, 2023])
    parser.add_argument("--output-dir", type=Path, default=Path("data/interim/lulc"))
    return parser.parse_args()


def fetch_year(catalog: Client, boundary: gpd.GeoDataFrame, year: int, output: Path) -> None:
    search = catalog.search(
        collections=[COLLECTION],
        intersects=mapping(boundary.to_crs("EPSG:4326").geometry.union_all()),
        datetime=f"{year}-01-01/{year}-12-31",
    )
    items = list(search.items())
    if not items:
        raise RuntimeError(f"没有找到 {year} 年覆盖永春县的土地覆盖数据")

    signed_item = planetary_computer.sign(items[0])
    asset_url = signed_item.assets["data"].href
    with rasterio.open(asset_url) as source:
        local_boundary = boundary.to_crs(source.crs)
        image, transform = mask(
            source,
            [mapping(geometry) for geometry in local_boundary.geometry],
            crop=True,
            nodata=0,
        )
        profile = source.profile.copy()
        profile.update(
            driver="GTiff",
            height=image.shape[1],
            width=image.shape[2],
            transform=transform,
            count=1,
            compress="deflate",
            tiled=True,
            nodata=0,
        )
        with rasterio.open(output, "w", **profile) as destination:
            destination.write(image)


def main() -> None:
    args = parse_args()
    boundary = gpd.read_file(args.boundary)
    if boundary.crs is None:
        raise ValueError("边界文件缺少坐标系")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    catalog = Client.open(STAC_URL)
    for year in args.years:
        output = args.output_dir / f"io_lulc_{year}_yongchun.tif"
        fetch_year(catalog, boundary, year, output)
        print(f"已生成：{output}")


if __name__ == "__main__":
    main()

