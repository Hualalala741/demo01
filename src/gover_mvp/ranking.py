from __future__ import annotations

from collections.abc import Mapping

import geopandas as gpd
import numpy as np


SCORE_COLUMNS = {
    "cost": "cost_score",
    "market": "market_score",
    "risk": "risk_score",
    "policy": "policy_score",
}


def is_explicit_true(values):
    return values.map(lambda value: value is True or str(value).strip().lower() in {"true", "1", "yes"})


def is_explicit_false(values):
    return values.map(lambda value: value is False or str(value).strip().lower() in {"false", "0", "no"})


def normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    clean = {key: max(0.0, float(weights.get(key, 0.0))) for key in SCORE_COLUMNS}
    total = sum(clean.values())
    if total == 0:
        return {key: 1 / len(clean) for key in clean}
    return {key: value / total for key, value in clean.items()}


def filter_candidates(
    candidates: gpd.GeoDataFrame,
    minimum_area_mu: float,
    require_irrigation: bool = False,
) -> gpd.GeoDataFrame:
    """执行MVP硬筛选；面积不足或已知不可行的土地直接淘汰。"""
    # unknown不是“通过”，但也不能被伪装成“不满足”；仅排除明确失败的记录。
    mask = (candidates["area_mu"] >= minimum_area_mu) & ~is_explicit_true(candidates["protected_overlap"])
    mask &= ~is_explicit_false(candidates["climate_pass"])
    mask &= ~is_explicit_false(candidates["soil_pass"])
    if require_irrigation and "irrigation_available" in candidates:
        mask &= ~is_explicit_false(candidates["irrigation_available"])
    return candidates.loc[mask].copy()


def rank_candidates(
    candidates: gpd.GeoDataFrame,
    weights: Mapping[str, float],
) -> gpd.GeoDataFrame:
    ranked = candidates.copy()
    normalized = normalize_weights(weights)
    total = np.zeros(len(ranked), dtype=float)
    for dimension, column in SCORE_COLUMNS.items():
        values = ranked[column].fillna(0).clip(0, 100).to_numpy(dtype=float)
        total += values * normalized[dimension]
    ranked["total_score"] = total.round(1)
    ranked = ranked.sort_values(["total_score", "area_mu"], ascending=[False, False])
    ranked["rank"] = np.arange(1, len(ranked) + 1)
    return ranked


def build_reason(row) -> str:
    dimensions = {
        "成本条件": float(row["cost_score"]),
        "市场可达性": float(row["market_score"]),
        "风险表现": float(row["risk_score"]),
        "政策匹配": float(row["policy_score"]),
    }
    if len(set(dimensions.values())) == 1:
        return "四项软排序指标当前为占位值，待接入真实数据后生成差异化解释。"
    strongest = max(dimensions, key=dimensions.get)
    weakest = min(dimensions, key=dimensions.get)
    return f"主要优势：{strongest}；相对短板：{weakest}。"
