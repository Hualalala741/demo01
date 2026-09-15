from __future__ import annotations

import numpy as np


def build_abandonment_mask(
    historical: np.ndarray,
    recent_layers: list[np.ndarray],
    valid_data: np.ndarray,
    historical_crop_values: list[int],
    recent_proxy_values: list[int],
) -> np.ndarray:
    """筛选历史为耕地且近年持续属于低利用代理类别的有效像素。"""
    historical_crop = np.isin(historical, historical_crop_values)
    persistently_non_crop = np.ones(historical.shape, dtype=bool)
    for recent in recent_layers:
        persistently_non_crop &= np.isin(recent, recent_proxy_values)
    return historical_crop & persistently_non_crop & valid_data

