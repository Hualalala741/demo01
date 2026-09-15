from __future__ import annotations

from pathlib import Path

import geopandas as gpd


REQUIRED_COLUMNS = {
    "land_id",
    "area_mu",
    "cost_score",
    "market_score",
    "risk_score",
    "policy_score",
    "protected_overlap",
    "climate_pass",
    "soil_pass",
}


def load_candidates(project_root: Path) -> tuple[gpd.GeoDataFrame, str]:
    """优先加载处理后的真实数据，否则加载明确标注的演示数据。"""
    ranked_path = project_root / "data" / "processed" / "yongchun_ranked.gpkg"
    real_path = project_root / "data" / "processed" / "yongchun_mvp.gpkg"
    demo_path = project_root / "data" / "demo" / "candidates.geojson"

    if ranked_path.exists():
        candidates = gpd.read_file(ranked_path, layer="candidate_lands")
        source_label = "真实候选地 + 第一版空间指标"
    elif real_path.exists():
        candidates = gpd.read_file(real_path, layer="candidate_lands")
        source_label = "处理后的候选地数据"
    elif demo_path.exists():
        candidates = gpd.read_file(demo_path)
        source_label = "演示候选地（非真实识别结果）"
    else:
        raise FileNotFoundError("未找到候选地数据，请先生成数据或恢复演示数据。")

    missing = REQUIRED_COLUMNS.difference(candidates.columns)
    if missing:
        raise ValueError(f"候选地缺少必要字段：{', '.join(sorted(missing))}")

    if candidates.crs is None:
        candidates = candidates.set_crs("EPSG:4326")
    return candidates.to_crs("EPSG:4326"), source_label
