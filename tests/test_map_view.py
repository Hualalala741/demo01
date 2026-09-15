from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from gover_mvp.data import load_county_boundary
from gover_mvp.map_view import build_map, geometry_thumbnail_svg


def map_candidates():
    return gpd.GeoDataFrame(
        {
            "rank": [1],
            "land_id": ["A"],
            "area_mu": [80.0],
            "total_score": [75.0],
            "cost_score": [80.0],
            "market_score": [70.0],
            "risk_score": [65.0],
            "policy_level": [3],
            "policy_score": [100.0],
            "reason": ["测试地块"],
        },
        geometry=[box(118.0, 25.2, 118.01, 25.21)],
        crs="EPSG:4326",
    )


def test_county_boundary_is_folium_serializable():
    project_root = Path(__file__).resolve().parents[1]
    boundary = load_county_boundary(project_root)

    assert list(boundary.columns) == ["name", "geometry"]
    assert boundary.iloc[0]["name"] == "永春县"


def test_map_defaults_to_satellite_and_adds_selected_layer():
    candidates = map_candidates()
    boundary = gpd.GeoDataFrame(
        {"name": ["永春县"]},
        geometry=[box(117.7, 25.1, 118.5, 25.6)],
        crs="EPSG:4326",
    )

    rendered = build_map(
        candidates,
        candidates,
        county_boundary=boundary,
        selected_land_id="A",
    ).get_root().render()

    assert "World_Imagery" in rendered
    assert r"\u6c38\u6625\u53bf\u8303\u56f4" in rendered
    assert r"\u5f53\u524d\u9009\u4e2d\u5730\u5757" in rendered
    assert '"maxZoom": 16' in rendered


def test_geometry_thumbnail_uses_real_polygon_shape():
    geometry = box(118.0, 25.2, 118.02, 25.21)

    svg = geometry_thumbnail_svg(geometry)

    assert 'aria-label="地块形状"' in svg
    assert "<path" in svg
    assert 'viewBox="0 0 180 108"' in svg
    assert "118.00" not in svg
    assert "fill-rule=\"evenodd\"" in svg
