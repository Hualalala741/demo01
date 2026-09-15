from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from gover_mvp.spatial_metrics import (
    METRIC_CRS,
    nearby_count,
    nearest_attribute,
    nearest_distance_km,
    population_in_radius,
    scale_score,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为候选地计算第一版soft ranking空间指标。")
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--population", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--land-costs", type=Path, default=Path("data/processed/land_transfer_samples.csv"))
    parser.add_argument("--county-context", type=Path, default=Path("data/processed/county_context.json"))
    return parser.parse_args()


def read_optional(path: Path, layer: str, crs: str) -> gpd.GeoDataFrame:
    try:
        return gpd.read_file(path, layer=layer).to_crs(crs)
    except Exception:
        return gpd.GeoDataFrame(geometry=[], crs=crs)


def main() -> None:
    args = parse_args()
    lands = gpd.read_file(args.candidates, layer="candidate_lands").to_crs(METRIC_CRS)
    centroids = gpd.GeoDataFrame(lands.drop(columns="geometry"), geometry=lands.centroid, crs=lands.crs)

    major_roads = read_optional(args.features, "major_roads", METRIC_CRS)
    highway_exits = read_optional(args.features, "highway_exits", METRIC_CRS)
    rivers = read_optional(args.features, "rivers", METRIC_CRS)
    settlements = read_optional(args.features, "settlements", METRIC_CRS)
    town_centers = read_optional(args.features, "town_centers", METRIC_CRS)
    markets = read_optional(args.features, "markets", METRIC_CRS)
    logistics = read_optional(args.features, "logistics", METRIC_CRS)
    agriculture = read_optional(args.features, "agriculture_pois", METRIC_CRS)

    lands["major_road_km"] = nearest_distance_km(centroids, major_roads)
    lands["highway_exit_km"] = nearest_distance_km(centroids, highway_exits)
    lands["settlement_km"] = nearest_distance_km(centroids, settlements)
    lands["town_name"] = nearest_attribute(centroids, town_centers, "name")
    lands["river_km"] = nearest_distance_km(centroids, rivers)
    lands["market_km"] = nearest_distance_km(centroids, markets)
    lands["logistics_km"] = nearest_distance_km(centroids, logistics)
    lands["agri_poi_10km"] = nearby_count(centroids, agriculture, 10_000)
    lands["population_5km"] = population_in_radius(centroids, args.population, 5_000)

    road_score = scale_score(lands["major_road_km"], higher_is_better=False)
    highway_score = scale_score(lands["highway_exit_km"], higher_is_better=False)
    settlement_score = scale_score(lands["settlement_km"], higher_is_better=False)
    population_score = scale_score(lands["population_5km"], higher_is_better=True)
    market_score = scale_score(lands["market_km"], higher_is_better=False)
    logistics_score = scale_score(lands["logistics_km"], higher_is_better=False)
    agri_score = scale_score(lands["agri_poi_10km"], higher_is_better=True)
    river_safety_score = scale_score(lands["river_km"].clip(upper=3), higher_is_better=True)

    transfers = pd.read_csv(args.land_costs)
    town_medians = transfers.groupby("town")["price_yuan_per_mu_year"].median()
    county_fallback = float(transfers["price_yuan_per_mu_year"].median())
    lands["land_rent_yuan_per_mu_year"] = lands["town_name"].map(town_medians).fillna(county_fallback)
    lands["land_rent_source_level"] = lands["town_name"].map(
        lambda town: "town" if town in town_medians.index else "county_sample_fallback"
    )
    land_cost_score = scale_score(lands["land_rent_yuan_per_mu_year"], higher_is_better=False)

    context = json.loads(args.county_context.read_text(encoding="utf-8"))
    minimum_wage = float(context["labor"]["minimum_wage_yuan_month"])
    wage_reference = context["labor"]["provincial_minimum_wage_tiers"]
    lands["minimum_wage_yuan_month"] = minimum_wage
    labor_cost_score = (max(wage_reference) - minimum_wage) / (max(wage_reference) - min(wage_reference)) * 100
    lands["labor_cost_score"] = round(labor_cost_score, 1)
    lands["nonresidential_water_yuan_ton"] = context["utilities"]["nonresidential_water_yuan_ton"]
    lands["agricultural_electricity_yuan_kwh"] = context["utilities"]["agricultural_electricity_low_voltage_yuan_kwh"]
    # 目前只有一个县，水电价格缺少横向样本，保留原值并给予中性归一化分，避免人为制造差异。
    lands["utility_cost_score"] = 50.0

    lands["cost_score"] = (
        road_score * 0.25
        + highway_score * 0.20
        + settlement_score * 0.10
        + land_cost_score * 0.20
        + labor_cost_score * 0.10
        + lands["utility_cost_score"] * 0.15
    ).round(1)
    lands["market_score"] = (
        population_score * 0.45 + market_score * 0.20 + logistics_score * 0.20 + agri_score * 0.15
    ).round(1)
    lands["climate_risk_score"] = context["climate_risk"]["normalized_safety_score"]
    lands["risk_score"] = (river_safety_score * 0.75 + lands["climate_risk_score"] * 0.25).round(1)
    lands["policy_score"] = 0.0  # 运行时根据作物和面积动态计算0—3级，再映射到0—100。
    lands["data_completeness"] = lands["land_rent_source_level"].map(
        {"town": 0.82, "county_sample_fallback": 0.74}
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()
    lands.to_crs("EPSG:4326").to_file(args.output, layer="candidate_lands", driver="GPKG")
    print(f"已写入 {len(lands)} 块土地及其空间指标：{args.output}")


if __name__ == "__main__":
    main()
