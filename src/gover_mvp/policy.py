from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd


CROP_OPTIONS = ["水稻", "玉米", "大豆", "甘薯", "马铃薯", "花生", "茶", "柑橘", "竹类"]
GRAIN_CROPS = {"水稻", "玉米", "大豆", "甘薯", "马铃薯", "花生", "旱稻"}


def load_policy_inputs(project_root: Path) -> tuple[list[dict], dict[str, dict]]:
    processed = project_root / "data" / "processed"
    policies = json.loads((processed / "planting_subsidies.json").read_text(encoding="utf-8"))
    continuity_rows = json.loads((processed / "policy_continuity.json").read_text(encoding="utf-8"))
    return policies, {row["crop"]: row for row in continuity_rows}


def crop_matches(scope: list[str], crop: str) -> bool:
    return crop in scope or (crop in GRAIN_CROPS and "粮食作物" in scope)


def policy_assessment(crop: str, area_mu: float, policies: list[dict], continuity: dict[str, dict]) -> dict:
    matching = [policy for policy in policies if crop_matches(policy["crop_scope"], crop)]
    eligible = [
        policy
        for policy in matching
        if area_mu >= float(policy["minimum_area_mu"])
        and (policy["maximum_area_mu"] is None or area_mu <= float(policy["maximum_area_mu"]))
    ]
    trend = continuity.get(crop, {})
    current_support = bool(trend.get("fifteenth_support", False))
    previous_support = bool(trend.get("fourteenth_support", False))

    if eligible:
        level = 3
        names = "、".join(sorted({policy["name"] for policy in eligible}))
        reason = f"符合公开补贴的作物与面积门槛：{names}。"
    elif matching or current_support:
        level = 2
        reason = "有明确产业政策，但当前面积未匹配已采集的补贴门槛。"
    elif previous_support and not current_support:
        level = 0
        reason = "十四五曾明确推进，但十五五未继续明确支持，本期按不建议开发处理。"
    else:
        level = 0
        reason = "当前采集范围内未找到相关产业政策。"

    if previous_support and not current_support:
        level = 0
        reason += " 十四五→十五五支持出现中断。"

    return {
        "policy_level": level,
        "policy_score": round(level / 3 * 100, 1),
        "policy_reason": reason,
        "policy_continuity": trend.get("trend", "未识别"),
        "eligible_policy_count": len(eligible),
    }


def apply_policy_scores(
    candidates: gpd.GeoDataFrame,
    crop: str,
    policies: list[dict],
    continuity: dict[str, dict],
) -> gpd.GeoDataFrame:
    result = candidates.copy()
    assessments = [policy_assessment(crop, float(area), policies, continuity) for area in result["area_mu"]]
    for key in assessments[0] if assessments else []:
        result[key] = [assessment[key] for assessment in assessments]
    return result


def apply_natural_resource_policy_scores(
    candidates: gpd.GeoDataFrame,
    crop: str,
    continuity: dict[str, dict],
) -> gpd.GeoDataFrame:
    """自然资源斑块未核定为耕地，只评价产业方向，不匹配耕地补贴。"""
    result = candidates.copy()
    trend = continuity.get(crop, {})
    current_support = bool(trend.get("fifteenth_support", False))
    previous_support = bool(trend.get("fourteenth_support", False))
    level = 2 if current_support else 0
    if previous_support and not current_support:
        level = 0
    result["policy_level"] = level
    result["policy_score"] = round(level / 3 * 100, 1)
    result["policy_reason"] = (
        "仅表示产业方向支持；该斑块尚未核定为耕地，不匹配撂荒复垦或耕地类补贴。"
    )
    result["policy_continuity"] = trend.get("trend", "未识别")
    result["eligible_policy_count"] = 0
    return result
