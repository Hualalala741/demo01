from __future__ import annotations

import folium
import geopandas as gpd
from branca.colormap import LinearColormap


def build_map(
    all_candidates: gpd.GeoDataFrame,
    ranked_candidates: gpd.GeoDataFrame,
) -> folium.Map:
    bounds = all_candidates.total_bounds
    center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
    map_object = folium.Map(
        location=center,
        zoom_start=11,
        tiles="OpenStreetMap",
        control_scale=True,
    )

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

    folium.LayerControl(collapsed=False).add_to(map_object)
    map_object.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    return map_object
