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


def build_stable_natural_resource_mask(
    annual_layers: list[np.ndarray],
    valid_data: np.ndarray,
    resource_values: list[int],
) -> np.ndarray:
    """筛选所有年度都稳定属于裸地/草灌地等资源代理类别的像素。"""
    if not annual_layers:
        raise ValueError("至少需要一个年度土地覆盖图层")
    stable_resource = np.ones(annual_layers[0].shape, dtype=bool)
    for layer in annual_layers:
        if layer.shape != annual_layers[0].shape:
            raise ValueError("年度土地覆盖图层尺寸不一致")
        stable_resource &= np.isin(layer, resource_values)
    return stable_resource & valid_data
