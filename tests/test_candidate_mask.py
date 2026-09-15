import numpy as np

from gover_mvp.candidates import build_abandonment_mask


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
