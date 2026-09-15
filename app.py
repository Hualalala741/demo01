from __future__ import annotations

from pathlib import Path

import streamlit as st
from streamlit_folium import st_folium

from gover_mvp.data import load_candidates
from gover_mvp.map_view import build_map
from gover_mvp.policy import CROP_OPTIONS, apply_policy_scores, load_policy_inputs
from gover_mvp.ranking import build_reason, filter_candidates, rank_candidates


PROJECT_ROOT = Path(__file__).resolve().parent

LAND_RENT_SOURCE_LABELS = {
    "village": "村级样本",
    "town": "乡镇样本中位数",
    "county_sample_fallback": "县内样本中位数回填",
}

st.set_page_config(page_title="永春县种植选址", page_icon="🌱", layout="wide")


def get_candidates():
    return load_candidates(PROJECT_ROOT)


def get_policy_inputs():
    return load_policy_inputs(PROJECT_ROOT)


st.title("永春县种植选址 MVP")
st.caption("从疑似撂荒候选地中执行面积硬筛选和多指标排序")

try:
    candidates, source_label = get_candidates()
    policies, policy_continuity = get_policy_inputs()
except (FileNotFoundError, ValueError) as error:
    st.error(str(error))
    st.stop()

with st.sidebar:
    st.header("企业需求")
    crop = st.selectbox("种植作物", CROP_OPTIONS)
    minimum_area = st.number_input("所需连续面积（亩）", min_value=1.0, max_value=5000.0, value=50.0, step=10.0)
    require_irrigation = st.checkbox("必须具备灌溉条件", value=False)

    st.subheader("排序偏好")
    cost_weight = st.slider("成本", 0, 100, 30)
    market_weight = st.slider("市场/收益", 0, 100, 30)
    risk_weight = st.slider("低风险", 0, 100, 25)
    policy_weight = st.slider("政策支持", 0, 100, 15)

    st.divider()
    st.caption(f"当前数据：{source_label}")
    if "protection_screened" in candidates and not candidates["protection_screened"].all():
        st.info("本版暂未纳入完整保护区边界；该约束保留为后续政府数据接口。")
    if any(str(candidates[column].iloc[0]).lower() == "unknown" for column in ("climate_pass", "soil_pass")):
        st.info("气候、土壤当前为 unknown：本版不据此淘汰，等待其他团队结果接入。")
    if require_irrigation and str(candidates["irrigation_available"].iloc[0]).lower() == "unknown":
        st.warning("灌溉条件尚无数据；已保留候选地并标记待核验，而不是误判为满足或不满足。")
    st.warning("遥感候选地不代表土地权属、规划用途或政府审批结论。")

weights = {
    "cost": cost_weight,
    "market": market_weight,
    "risk": risk_weight,
    "policy": policy_weight,
}
candidates = apply_policy_scores(candidates, crop, policies, policy_continuity)
eligible = filter_candidates(candidates, minimum_area, require_irrigation)
ranked = rank_candidates(eligible, weights)
if not ranked.empty:
    ranked["reason"] = ranked.apply(build_reason, axis=1)

metric_a, metric_b, metric_c, metric_d = st.columns(4)
metric_a.metric("识别候选地", len(candidates))
metric_b.metric("通过硬筛选", len(ranked))
metric_c.metric("面积要求", f"≥ {minimum_area:g} 亩")
metric_d.metric("当前作物", crop)

map_column, result_column = st.columns([2.2, 1], gap="large")
with map_column:
    st.subheader("候选土地地图")
    interactive_map = build_map(candidates, ranked)
    st_folium(interactive_map, height=650, width="stretch", returned_objects=[])

with result_column:
    st.subheader("推荐结果")
    if ranked.empty:
        st.info("没有土地通过当前条件，请降低面积要求或取消灌溉硬约束。")
    else:
        for _, row in ranked.head(5).iterrows():
            with st.container(border=True):
                st.markdown(f"### #{int(row['rank'])} · {row['land_id']}")
                st.write(f"**{row['area_mu']:.1f} 亩** · 综合得分 **{row['total_score']:.1f}**")
                st.progress(float(row["total_score"]) / 100)
                st.caption(row["reason"])
                st.write(
                    f"成本 {row['cost_score']:.0f} ｜ 市场 {row['market_score']:.0f} ｜ "
                    f"风险 {row['risk_score']:.0f} ｜ 政策 {int(row['policy_level'])}/3"
                )
                st.caption(f"政策连续性：{row['policy_continuity']}。{row['policy_reason']}")
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
        "town_name",
        "land_rent_yuan_per_mu_year",
        "land_rent_source_level",
        "data_completeness",
    ]
    st.dataframe(ranked[display_columns], hide_index=True, width="stretch")

st.caption("MVP结果仅用于技术可行性验证，正式选址须结合政府提供的权属、规划与审批数据复核。")
