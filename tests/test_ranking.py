import geopandas as gpd
from shapely.geometry import box

from gover_mvp.ranking import build_reason, filter_candidates, normalize_weights, rank_candidates


def sample_candidates():
    return gpd.GeoDataFrame(
        {
            "land_id": ["A", "B", "C"],
            "area_mu": [80.0, 40.0, 120.0],
            "protected_overlap": [False, False, True],
            "climate_pass": [True, True, True],
            "soil_pass": [True, True, True],
            "irrigation_available": [True, False, True],
            "cost_score": [90.0, 50.0, 80.0],
            "market_score": [60.0, 80.0, 70.0],
            "risk_score": [70.0, 70.0, 70.0],
            "policy_score": [50.0, 50.0, 50.0],
        },
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1), box(2, 0, 3, 1)],
        crs="EPSG:4326",
    )


def test_area_and_protection_are_hard_filters():
    eligible = filter_candidates(sample_candidates(), minimum_area_mu=50)
    assert eligible["land_id"].tolist() == ["A"]


def test_irrigation_can_be_required():
    eligible = filter_candidates(sample_candidates(), minimum_area_mu=1, require_irrigation=True)
    assert eligible["land_id"].tolist() == ["A"]


def test_unknown_is_not_silently_converted_to_failure():
    candidates = sample_candidates().iloc[:1].copy()
    candidates["protected_overlap"] = "unknown"
    candidates["climate_pass"] = "unknown"
    candidates["soil_pass"] = "unknown"
    candidates["irrigation_available"] = "unknown"
    eligible = filter_candidates(candidates, minimum_area_mu=1, require_irrigation=True)
    assert eligible["land_id"].tolist() == ["A"]


def test_ranking_uses_normalized_weights():
    candidates = sample_candidates().iloc[:2].copy()
    ranked = rank_candidates(candidates, {"cost": 100, "market": 0, "risk": 0, "policy": 0})
    assert ranked.iloc[0]["land_id"] == "A"
    assert ranked.iloc[0]["total_score"] == 90.0


def test_zero_weights_fall_back_to_equal_weights():
    weights = normalize_weights({"cost": 0, "market": 0, "risk": 0, "policy": 0})
    assert weights == {"cost": 0.25, "market": 0.25, "risk": 0.25, "policy": 0.25}


def test_equal_placeholder_scores_have_honest_explanation():
    row = sample_candidates().iloc[0].copy()
    for column in ("cost_score", "market_score", "risk_score", "policy_score"):
        row[column] = 50
    assert "占位值" in build_reason(row)
