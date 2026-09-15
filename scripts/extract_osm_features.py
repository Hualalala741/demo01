from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio


MAJOR_ROADS = {"motorway", "trunk", "primary", "secondary", "tertiary"}
SETTLEMENTS = {"city", "town", "village"}
MARKET_PATTERN = r"市场|农贸|批发|market"
LOGISTICS_PATTERN = r"物流|冷链|仓储|配送|快递|logistic|warehouse"
AGRICULTURE_PATTERN = r"合作社|农业|农场|茶厂|果业|农产品|种植|farm|agricultur"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从福建OSM离线包提取永春县soft ranking空间要素。")
    parser.add_argument("--pbf", type=Path, required=True)
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/processed/osm_features.gpkg"))
    return parser.parse_args()


def clip_to_boundary(frame: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if frame.empty:
        return frame
    return gpd.clip(frame, boundary.to_crs(frame.crs), keep_geom_type=False).reset_index(drop=True)


def text_blob(frame: gpd.GeoDataFrame) -> pd.Series:
    return frame["name"].fillna("").astype(str) + " " + frame["other_tags"].fillna("").astype(str)


def poi_points(frame: gpd.GeoDataFrame, pattern: str) -> gpd.GeoDataFrame:
    selected = frame.loc[text_blob(frame).str.contains(pattern, case=False, regex=True)].copy()
    if not selected.empty and not (selected.geom_type == "Point").all():
        selected.geometry = selected.geometry.representative_point()
    return selected[["osm_id", "name", "other_tags", "geometry"]]


def write_layer(frame: gpd.GeoDataFrame, output: Path, layer: str) -> None:
    if frame.empty:
        return
    frame.to_file(output, layer=layer, driver="GPKG", mode="w" if not output.exists() else "a")


def main() -> None:
    args = parse_args()
    boundary = gpd.read_file(args.boundary).to_crs("EPSG:4326")
    bbox = tuple(boundary.total_bounds)

    points = clip_to_boundary(pyogrio.read_dataframe(args.pbf, layer="points", bbox=bbox), boundary)
    lines = clip_to_boundary(pyogrio.read_dataframe(args.pbf, layer="lines", bbox=bbox), boundary)
    polygons = clip_to_boundary(pyogrio.read_dataframe(args.pbf, layer="multipolygons", bbox=bbox), boundary)

    roads = lines.loc[lines["highway"].notna()].copy()
    major_roads = roads.loc[roads["highway"].isin(MAJOR_ROADS)].copy()
    highway_exits = points.loc[points["highway"].eq("motorway_junction")].copy()
    rivers = lines.loc[lines["waterway"].isin({"river", "stream", "canal"})].copy()
    settlements = points.loc[points["place"].isin(SETTLEMENTS)].copy()
    town_centers = points.loc[points["place"].eq("town") & points["name"].notna()].copy()

    poi_source = pd.concat([points, polygons], ignore_index=True)
    poi_source = gpd.GeoDataFrame(poi_source, geometry="geometry", crs=points.crs)
    markets = poi_points(poi_source, MARKET_PATTERN)
    logistics = poi_points(poi_source, LOGISTICS_PATTERN)
    agriculture = poi_points(poi_source, AGRICULTURE_PATTERN)

    if args.output.exists():
        args.output.unlink()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for layer, frame in {
        "roads": roads,
        "major_roads": major_roads,
        "highway_exits": highway_exits,
        "rivers": rivers,
        "settlements": settlements,
        "town_centers": town_centers,
        "markets": markets,
        "logistics": logistics,
        "agriculture_pois": agriculture,
    }.items():
        write_layer(frame, args.output, layer)
        print(f"{layer}: {len(frame)}")


if __name__ == "__main__":
    main()
