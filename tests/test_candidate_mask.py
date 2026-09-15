import numpy as np

from gover_mvp.candidates import (
    build_abandonment_mask,
    build_stable_natural_resource_mask,
)


def test_candidate_requires_historical_crop_and_persistent_proxy_class():
    historical = np.array([[5, 5, 2], [5, 5, 5]], dtype="uint8")
    recent_2022 = np.array([[11, 11, 11], [8, 5, 8]], dtype="uint8")
    recent_2023 = np.array([[11, 5, 11], [8, 11, 8]], dtype="uint8")
    valid = np.ones((2, 3), dtype=bool)

    result = build_abandonment_mask(
        historical,
        [recent_2022, recent_2023],
        valid,
        historical_crop_values=[5],
        recent_proxy_values=[8, 11],
    )

    expected = np.array([[True, False, False], [True, False, True]])
    np.testing.assert_array_equal(result, expected)


def test_stable_natural_resources_require_every_year_and_exclude_trees():
    annual_2017 = np.array([[8, 11, 2], [8, 5, 11]], dtype="uint8")
    annual_2022 = np.array([[11, 11, 8], [8, 8, 11]], dtype="uint8")
    annual_2023 = np.array([[8, 2, 8], [11, 8, 11]], dtype="uint8")
    valid = np.ones((2, 3), dtype=bool)

    result = build_stable_natural_resource_mask(
        [annual_2017, annual_2022, annual_2023],
        valid,
        resource_values=[8, 11],
    )

    expected = np.array([[True, False, False], [True, False, True]])
    np.testing.assert_array_equal(result, expected)
