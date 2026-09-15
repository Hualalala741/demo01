from __future__ import annotations

from pathlib import Path

import streamlit as st
from streamlit_folium import st_folium

from gover_mvp.data import load_candidates, load_county_boundary
from gover_mvp.map_view import build_map, geometry_thumbnail_svg
from gover_mvp.policy_profile import compare_plan_mentions, load_industry_profile
from gover_mvp.ranking import build_reason, filter_candidates, rank_candidates


PROJECT_ROOT = Path(__file__).resolve().parent

LAND_RENT_SOURCE_LABELS = {
    "village": "村级样本",
    "town": "乡镇样本中位数",
    "county_sample_fallback": "县内样本中位数回填",
}

st.set_page_config(page_title="永春县资源选址Demo", page_icon="🌱", layout="wide")

st.markdown(
    """
    <style>
    div[class*="st-key-land_card_"] {
        position: relative;
        cursor: pointer;
        transition: border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
    }
    div[class*="st-key-land_card_"]:has(button:hover) {
        border-color: #4b8b3b;
        box-shadow: 0 4px 14px rgba(38, 92, 48, 0.14);
        transform: translateY(-1px);
    }
    div[class*="st-key-land_card_"] > div[class*="st-key-focus_"] {
        position: absolute;
        inset: 0;
        z-index: 20;
        width: auto;
        height: auto;
    }
    div[class*="st-key-land_card_"] > div[class*="st-key-focus_"] div[data-testid="stButton"] {
        position: static;
        width: 100%;
        height: 100%;
    }
    div[class*="st-key-land_card_"] div[data-testid="stButton"] button {
        width: 100%;
        height: 100%;
        min-height: 100%;
        border: 0;
        opacity: 0;
        cursor: pointer;
    }
    .land-card-title {
        color: #1f2937;
        font-size: 1.3rem;
        font-weight: 700;
        line-height: 1.25;
        margin: 0.2rem 0 0.75rem;
        overflow-wrap: anywhere;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_candidates(candidate_type: str):
    return load_candidates(PROJECT_ROOT, candidate_type)


@st.cache_data
def get_industry_profiles():
    return {
        "fourteenth": load_industry_profile(PROJECT_ROOT, "2021-2025"),
        "fifteenth": load_industry_profile(PROJECT_ROOT, "2026-2030"),
    }


def get_county_boundary():
    return load_county_boundary(PROJECT_ROOT)


def select_land(land_id: str | None) -> None:
    st.session_state["selected_land_id"] = land_id


st.title("永春县资源选址Demo")

with st.sidebar:
    st.header("企业需求")
    resource_label = st.selectbox(
        "候选资源类型",
        ["疑似撂荒耕地", "稳定裸地/草灌地（潜在资源）"],
    )

candidate_type = (
    "stable_natural_resource"
    if resource_label == "稳定裸地/草灌地（潜在资源）"
    else "abandoned_cropland"
)

try:
    candidates, source_label = get_candidates(candidate_type)
    industry_profiles = get_industry_profiles()
    county_boundary = get_county_boundary()
except (FileNotFoundError, ValueError) as error:
    st.error(str(error))
    st.stop()

if candidate_type == "stable_natural_resource":
    st.caption("从连续三年稳定为裸地或草灌地的遥感斑块中执行面积筛选和多指标排序")
else:
    st.caption("从疑似撂荒候选地中执行面积硬筛选和多指标排序")

with st.sidebar:
    industry_query = st.text_input("投资行业", value="竹子", placeholder="例如：竹子、陶瓷、电子信息")
    plan_mentions = compare_plan_mentions(
        industry_query,
        industry_profiles["fourteenth"],
        industry_profiles["fifteenth"],
    )
    fourteenth_match = plan_mentions["fourteenth"]
    industry_match = plan_mentions["fifteenth"]
    if fourteenth_match and industry_match:
        policy_status, policy_level = "十四五、十五五均提及", 2
    elif industry_match:
        policy_status, policy_level = "十五五新增", 3
    elif fourteenth_match:
        policy_status, policy_level = "十四五提及，十五五未提及", 1
    else:
        policy_status, policy_level = "未提及", 0
    policy_score = round(policy_level / 3 * 100, 1)
    if industry_query.strip():
        st.caption(
            "十四五："
            + (f"已提及 · {fourteenth_match['industry']}" if fourteenth_match else "未检索到")
            + " ｜ 十五五："
            + (f"已提及 · {industry_match['industry']}" if industry_match else "未检索到")
        )
        st.info(f"政策：{policy_status}（{policy_level}分）")
    if industry_match:
        st.success(f"十五五画像：{industry_match['industry']}")
        if industry_match.get("parent_industry"):
            st.caption(f"所属领域：{industry_match['parent_industry']}")
        st.caption(industry_match.get("development_goal", ""))
        with st.expander("查看画像内容"):
            if industry_match.get("development_directions"):
                st.write("发展方向：" + "、".join(industry_match["development_directions"]))
            if industry_match.get("planned_projects"):
                st.write("相关项目：" + "、".join(industry_match["planned_projects"]))
            st.write(f"来源文件：{industry_match['source_document']}")
    elif industry_query.strip():
        st.info("当前十五五产业画像中未检索到该行业。")
    else:
        st.info("请输入一个行业。")
    minimum_area = st.number_input(
        "所需连续面积（亩）",
        min_value=1.0,
        max_value=5000.0,
        value=50.0,
        step=10.0,
    )
    st.subheader("排序偏好")
    cost_weight = st.slider("成本", 0, 100, 30)
    market_weight = st.slider("市场/收益", 0, 100, 30)
    risk_weight = st.slider("低风险", 0, 100, 25)
    policy_weight = st.slider("政策", 0, 100, 15)

    st.divider()
    st.caption(f"当前数据：{source_label}")
    if candidate_type == "stable_natural_resource":
        st.info(
            "本类仅包含2017、2022、2023连续为裸地或草灌地的20—500亩斑块，"
            "已排除Trees；尚未接入坡度、法定地类、权属和国土空间规划。"
        )
    if "protection_screened" in candidates and not candidates["protection_screened"].all():
        st.info("本版暂未纳入完整保护区边界；该约束保留为后续政府数据接口。")
    if any(str(candidates[column].iloc[0]).lower() == "unknown" for column in ("climate_pass", "soil_pass")):
        st.info("气候、土壤当前为 unknown：本版不据此淘汰，等待其他团队结果接入。")
    st.warning("遥感候选地不代表土地权属、规划用途或政府审批结论。")

weights = {
    "cost": cost_weight,
    "market": market_weight,
    "risk": risk_weight,
    "policy": policy_weight,
}
candidates = candidates.copy()
candidates["policy_level"] = policy_level
candidates["policy_score"] = policy_score
candidates["policy_status"] = policy_status
candidates["policy_profile_industry"] = industry_match["industry"] if industry_match else ""
candidates["policy_reason"] = f"政策：{policy_status}。"
eligible = filter_candidates(candidates, minimum_area)
ranked = rank_candidates(eligible, weights)
if not ranked.empty:
    ranked["reason"] = ranked.apply(build_reason, axis=1)

metric_a, metric_b, metric_c, metric_d = st.columns(4)
metric_a.metric("识别资源斑块", len(candidates))
metric_b.metric("通过硬筛选", len(ranked))
metric_c.metric("面积要求", f"≥ {minimum_area:g} 亩")
metric_d.metric("当前行业", industry_query or "未填写")

result_column, map_column = st.columns([1.15, 1.4], gap="large")
with result_column:
    st.subheader("推荐结果")
    with st.container(height=650, border=False):
        if ranked.empty:
            st.info("没有土地通过当前条件，请降低面积要求。")
        else:
            for _, row in ranked.head(5).iterrows():
                with st.container(border=True, key=f"land_card_{row['land_id']}"):
                    st.button(
                        f"选择推荐地块 {row['land_id']}",
                        key=f"focus_{row['land_id']}",
                        on_click=select_land,
                        args=(str(row["land_id"]),),
                    )
                    card_text, card_shape = st.columns([1.7, 1], gap="small", vertical_alignment="top")
                    with card_text:
                        st.markdown(
                            f'<div class="land-card-title">#{int(row["rank"])} · {row["land_id"]}</div>',
                            unsafe_allow_html=True,
                        )
                        st.write(f"**{row['area_mu']:.1f} 亩** · 综合得分 **{row['total_score']:.1f}**")
                    with card_shape:
                        st.markdown(geometry_thumbnail_svg(row.geometry), unsafe_allow_html=True)
                    st.progress(float(row["total_score"]) / 100)
                    st.caption(row["reason"])
                    st.write(
                        f"成本 {row['cost_score']:.0f} ｜ 市场 {row['market_score']:.0f} ｜ "
                        f"风险 {row['risk_score']:.0f} ｜ 政策 {int(row['policy_level'])}/3"
                    )
                    st.caption(f"政策：{row['policy_status']}")
                    if "major_road_km" in row.index:
                        st.caption(
                            f"距主干道 {row['major_road_km']:.2f} km ｜ "
                            f"距高速出入口 {row['highway_exit_km']:.2f} km ｜ "
                            f"距居民点 {row['settlement_km']:.2f} km ｜ "
                            f"距河流 {row['river_km']:.2f} km ｜ "
                            f"周边5 km人口约 {row['population_5km']:,.0f}"
                        )
                        st.caption(
                            f"土地成本代理 {row['land_rent_yuan_per_mu_year']:.0f} 元/亩/年"
                            f"（{LAND_RENT_SOURCE_LABELS.get(row['land_rent_source_level'], row['land_rent_source_level'])}）｜"
                            f"最低工资 {row['minimum_wage_yuan_month']:.0f} 元/月｜"
                            f"非居民水价 {row['nonresidential_water_yuan_ton']:.2f} 元/吨｜"
                            f"农业电价 {row['agricultural_electricity_yuan_kwh']:.4f} 元/千瓦时"
                        )
                    if st.session_state.get("selected_land_id") == str(row["land_id"]):
                        st.caption("✓ 当前地图显示")

with map_column:
    map_title, map_action = st.columns([4, 1])
    with map_title:
        st.subheader("地块卫星影像")
    with map_action:
        st.button(
            "查看全县",
            on_click=select_land,
            args=(None,),
            use_container_width=True,
        )

    selected_land_id = st.session_state.get("selected_land_id")
    valid_land_ids = set(ranked["land_id"].astype(str))
    if selected_land_id not in valid_land_ids:
        selected_land_id = None
        st.session_state["selected_land_id"] = None

    if selected_land_id is None:
        st.caption("当前显示永春县全域；点击左侧推荐卡片可聚焦并高亮对应资源斑块。")
    else:
        selected_row = ranked.loc[ranked["land_id"].astype(str) == selected_land_id].iloc[0]
        st.caption(
            f"当前聚焦 #{int(selected_row['rank'])} · {selected_land_id} · "
            f"{selected_row['area_mu']:.1f} 亩"
        )

    interactive_map = build_map(
        candidates,
        ranked,
        county_boundary=county_boundary,
        selected_land_id=selected_land_id,
    )
    st_folium(
        interactive_map,
        height=560,
        width="stretch",
        returned_objects=[],
        key=f"candidate_map_{selected_land_id or 'county'}",
    )
    st.caption(
        "影像来源：Esri World Imagery 在线影像服务。县城代表点当前元数据为 "
        "2023-12-02、0.5 米、Vivid（Vantor / WV02）；县内不同位置和缩放级别的影像日期可能不同。"
    )

with st.expander("查看全部通过筛选的土地数据"):
    display_columns = [
        "rank",
        "land_id",
        "area_mu",
        "total_score",
        "cost_score",
        "market_score",
        "risk_score",
        "policy_score",
        "policy_level",
        "policy_status",
        "policy_profile_industry",
        "town_name",
        "land_rent_yuan_per_mu_year",
        "land_rent_source_level",
        "data_completeness",
    ]
    st.dataframe(ranked[display_columns], hide_index=True, width="stretch")
