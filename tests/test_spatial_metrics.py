import numpy as np
import pandas as pd

from gover_mvp.spatial_metrics import scale_score


def test_scale_score_respects_direction():
    values = pd.Series([1.0, 2.0, 3.0])
    assert scale_score(values, higher_is_better=True).tolist() == [0.0, 50.0, 100.0]
    assert scale_score(values, higher_is_better=False).tolist() == [100.0, 50.0, 0.0]


def test_scale_score_handles_missing_and_constant_values():
    constant = pd.Series([4.0, 4.0, np.nan])
    assert scale_score(constant, higher_is_better=True).tolist() == [50.0, 50.0, 50.0]

