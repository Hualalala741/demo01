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


def load_candidates(
    project_root: Path,
    candidate_type: str = "abandoned_cropland",
) -> tuple[gpd.GeoDataFrame, str]:
    """优先加载处理后的真实数据，否则加载明确标注的演示数据。"""
    if candidate_type == "stable_natural_resource":
        ranked_path = project_root / "data" / "processed" / "natural_resources_ranked.gpkg"
        real_path = project_root / "data" / "processed" / "natural_resources_mvp.gpkg"
        if ranked_path.exists():
            candidates = gpd.read_file(ranked_path, layer="candidate_lands")
            source_label = "稳定裸地/草灌地 + 第一版空间指标"
        elif real_path.exists():
            candidates = gpd.read_file(real_path, layer="candidate_lands")
            source_label = "稳定裸地/草灌地潜在资源"
        else:
            raise FileNotFoundError("未找到潜在自然资源数据，请先运行 build_natural_resources.py。")
        return _validate_candidates(candidates, source_label)

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

    return _validate_candidates(candidates, source_label)


def _validate_candidates(
    candidates: gpd.GeoDataFrame,
    source_label: str,
) -> tuple[gpd.GeoDataFrame, str]:
    missing = REQUIRED_COLUMNS.difference(candidates.columns)
    if missing:
        raise ValueError(f"候选地缺少必要字段：{', '.join(sorted(missing))}")

    if candidates.crs is None:
        candidates = candidates.set_crs("EPSG:4326")
    return candidates.to_crs("EPSG:4326"), source_label


def load_county_boundary(project_root: Path) -> gpd.GeoDataFrame:
    """加载永春县行政边界，用于地图范围和边界展示。"""
    boundary_path = project_root / "data" / "raw" / "yongchun_boundary.geojson"
    if not boundary_path.exists():
        raise FileNotFoundError("未找到永春县边界数据：data/raw/yongchun_boundary.geojson")

    boundary = gpd.read_file(boundary_path)
    if boundary.empty:
        raise ValueError("永春县边界数据为空。")
    if boundary.crs is None:
        boundary = boundary.set_crs("EPSG:4326")
    boundary = boundary.to_crs("EPSG:4326")
    # 上游行政区文件还包含 center/centroid 等 ndarray 字段，Folium 无法直接
    # JSON 序列化；地图只需要名称和几何。
    columns = [column for column in ("name", "geometry") if column in boundary.columns]
    return boundary[columns].copy()
