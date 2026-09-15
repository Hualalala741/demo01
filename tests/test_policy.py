import geopandas as gpd
from shapely.geometry import Point

from gover_mvp.policy import apply_natural_resource_policy_scores, apply_policy_scores, policy_assessment


POLICIES = [
    {
        "name": "玉米补贴",
        "crop_scope": ["玉米"],
        "minimum_area_mu": 30,
        "maximum_area_mu": None,
    }
]


def test_policy_level_three_is_normalized_to_100():
    continuity = {"玉米": {"fourteenth_support": True, "fifteenth_support": True, "trend": "连续支持"}}
    result = policy_assessment("玉米", 50, POLICIES, continuity)
    assert result["policy_level"] == 3
    assert result["policy_score"] == 100


def test_policy_discontinuity_sets_not_recommended_level_zero():
    continuity = {"测试作物": {"fourteenth_support": True, "fifteenth_support": False, "trend": "支持中断"}}
    result = policy_assessment("测试作物", 50, [], continuity)
    assert result["policy_level"] == 0
    assert result["policy_score"] == 0


def test_policy_is_calculated_for_each_land_area():
    lands = gpd.GeoDataFrame({"area_mu": [20, 50]}, geometry=[Point(0, 0), Point(1, 1)], crs=4326)
    continuity = {"玉米": {"fourteenth_support": True, "fifteenth_support": True, "trend": "连续支持"}}
    scored = apply_policy_scores(lands, "玉米", POLICIES, continuity)
    assert scored["policy_level"].tolist() == [2, 3]


def test_natural_resources_do_not_claim_cropland_subsidy_eligibility():
    lands = gpd.GeoDataFrame({"area_mu": [80]}, geometry=[Point(0, 0)], crs=4326)
    continuity = {"玉米": {"fourteenth_support": True, "fifteenth_support": True, "trend": "连续支持"}}

    scored = apply_natural_resource_policy_scores(lands, "玉米", continuity)

    assert scored.iloc[0]["policy_level"] == 2
    assert scored.iloc[0]["eligible_policy_count"] == 0
    assert "尚未核定为耕地" in scored.iloc[0]["policy_reason"]
