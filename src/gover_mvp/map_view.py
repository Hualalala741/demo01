from __future__ import annotations

import folium
import geopandas as gpd
from branca.colormap import LinearColormap
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry


def geometry_thumbnail_svg(
    geometry: BaseGeometry,
    width: int = 180,
    height: int = 108,
    padding: int = 8,
) -> str:
    """将真实地块几何缩放为适合推荐卡片展示的 SVG 缩略图。"""
    if geometry is None or geometry.is_empty:
        return ""

    if isinstance(geometry, Polygon):
        polygons = [geometry]
    elif isinstance(geometry, MultiPolygon):
        polygons = list(geometry.geoms)
    else:
        polygons = [part for part in geometry.geoms if isinstance(part, Polygon)]
    if not polygons:
        return ""

    min_x, min_y, max_x, max_y = geometry.bounds
    span_x = max(max_x - min_x, 1e-12)
    span_y = max(max_y - min_y, 1e-12)
    scale = min((width - 2 * padding) / span_x, (height - 2 * padding) / span_y)
    drawing_width = span_x * scale
    drawing_height = span_y * scale
    offset_x = (width - drawing_width) / 2
    offset_y = (height - drawing_height) / 2

    def ring_path(coordinates) -> str:
        points = [
            (
                offset_x + (x - min_x) * scale,
                height - offset_y - (y - min_y) * scale,
            )
            for x, y, *_ in coordinates
        ]
        if not points:
            return ""
        commands = [f"M {points[0][0]:.2f} {points[0][1]:.2f}"]
        commands.extend(f"L {x:.2f} {y:.2f}" for x, y in points[1:])
        commands.append("Z")
        return " ".join(commands)

    path_parts = []
    for polygon in polygons:
        path_parts.append(ring_path(polygon.exterior.coords))
        path_parts.extend(ring_path(interior.coords) for interior in polygon.interiors)
    path_data = " ".join(part for part in path_parts if part)

    return f"""
    <div style="display:flex;justify-content:flex-end;align-items:flex-start;width:100%;">
      <svg viewBox="0 0 {width} {height}" role="img" aria-label="地块形状"
           style="width:100%;max-width:{width}px;height:auto;min-height:82px;">
        <path d="{path_data}" fill="#65a95a" fill-opacity="0.78"
              stroke="#245c2f" stroke-width="3" stroke-linejoin="round"
              vector-effect="non-scaling-stroke" fill-rule="evenodd" />
      </svg>
    </div>
    """


def build_map(
    all_candidates: gpd.GeoDataFrame,
    ranked_candidates: gpd.GeoDataFrame,
    county_boundary: gpd.GeoDataFrame | None = None,
    selected_land_id: str | None = None,
) -> folium.Map:
    overview_geometry = county_boundary if county_boundary is not None and not county_boundary.empty else all_candidates
    bounds = overview_geometry.total_bounds
    center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
    map_object = folium.Map(
        location=center,
        zoom_start=11,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
    )

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, Maxar, Earthstar Geographics, and the GIS User Community",
        name="卫星影像",
        overlay=False,
        control=True,
        show=True,
        max_zoom=19,
    ).add_to(map_object)
    folium.TileLayer(
        tiles="OpenStreetMap",
        name="道路地图",
        overlay=False,
        control=True,
        show=False,
    ).add_to(map_object)

    if county_boundary is not None and not county_boundary.empty:
        folium.GeoJson(
            county_boundary,
            name="永春县范围",
            style_function=lambda _: {
                "fillColor": "#ffffff",
                "color": "#f8fafc",
                "weight": 3,
                "dashArray": "8 6",
                "fillOpacity": 0.03,
            },
            tooltip="永春县行政范围",
        ).add_to(map_object)

    folium.GeoJson(
        all_candidates,
        name="全部候选地",
        style_function=lambda _: {
            "fillColor": "#cbd5e1",
            "color": "#64748b",
            "weight": 1,
            "fillOpacity": 0.18,
        },
        tooltip=folium.GeoJsonTooltip(fields=["land_id", "area_mu"], aliases=["土地编号", "面积（亩）"]),
    ).add_to(map_object)

    if not ranked_candidates.empty:
        minimum = float(ranked_candidates["total_score"].min())
        maximum = float(ranked_candidates["total_score"].max())
        if minimum == maximum:
            minimum = max(0.0, minimum - 1)
        colormap = LinearColormap(["#fde68a", "#f59e0b", "#166534"], vmin=minimum, vmax=maximum)
        colormap.caption = "候选土地综合得分"
        colormap.add_to(map_object)

        fields = [
            "rank",
            "land_id",
            "area_mu",
            "total_score",
            "cost_score",
            "market_score",
            "risk_score",
            "policy_level",
            "policy_score",
            "reason",
        ]
        aliases = [
            "排名",
            "土地编号",
            "面积（亩）",
            "综合得分",
            "成本归一化分",
            "市场/收益归一化分",
            "低风险归一化分",
            "政策等级（0—3）",
            "政策归一化分",
            "说明",
        ]
        optional_popup_fields = [
            ("major_road_km", "距主干道（公里）"),
            ("settlement_km", "距居民点（公里）"),
            ("river_km", "距河流（公里）"),
            ("population_5km", "周边5公里人口代理"),
        ]
        for field, alias in optional_popup_fields:
            if field in ranked_candidates.columns:
                fields.append(field)
                aliases.append(alias)
        folium.GeoJson(
            ranked_candidates,
            name="通过筛选的土地",
            style_function=lambda feature: {
                "fillColor": colormap(feature["properties"]["total_score"]),
                "color": "#14532d",
                "weight": 2,
                "fillOpacity": 0.72,
            },
            highlight_function=lambda _: {"weight": 4, "fillOpacity": 0.9},
            tooltip=folium.GeoJsonTooltip(fields=fields[:4], aliases=aliases[:4], sticky=False),
            popup=folium.GeoJsonPopup(fields=fields, aliases=aliases, localize=True),
        ).add_to(map_object)

        if selected_land_id is not None:
            selected = ranked_candidates.loc[
                ranked_candidates["land_id"].astype(str) == str(selected_land_id)
            ]
            if not selected.empty:
                folium.GeoJson(
                    selected,
                    name="当前选中地块",
                    style_function=lambda _: {
                        "fillColor": "#22c55e",
                        "color": "#ffffff",
                        "weight": 5,
                        "fillOpacity": 0.42,
                    },
                    tooltip=folium.GeoJsonTooltip(
                        fields=["rank", "land_id", "area_mu", "total_score"],
                        aliases=["排名", "土地编号", "面积（亩）", "综合得分"],
                        sticky=False,
                    ),
                ).add_to(map_object)

                selected_bounds = selected.total_bounds
                map_object.fit_bounds(
                    [
                        [selected_bounds[1], selected_bounds[0]],
                        [selected_bounds[3], selected_bounds[2]],
                    ],
                    padding=(48, 48),
                    max_zoom=16,
                )

    folium.LayerControl(collapsed=False).add_to(map_object)
    if selected_land_id is None or ranked_candidates.empty:
        map_object.fit_bounds(
            [[bounds[1], bounds[0]], [bounds[3], bounds[2]]],
            padding=(16, 16),
        )
    return map_object
