"""
1D 信号処理ユーティリティ（SciPy 非依存）。

役割: プロファイル平滑化・feasibility 数値微分で共有する畳み込み。
働き: physics / smoothing から gaussian_filter1d を import する。
"""

from __future__ import annotations

import numpy as np


def gaussian_filter1d(x: np.ndarray, sigma: float) -> np.ndarray:
    """1D Gaussian smoothing with nearest edge handling (SciPy-free)."""
    x = np.asarray(x, dtype=float)
    sigma = float(sigma)
    if not np.isfinite(sigma) or sigma <= 0.0:
        return x
    radius = int(max(3, round(4.0 * sigma)))
    xs = np.arange(-radius, radius + 1, dtype=float)
    k = np.exp(-0.5 * (xs / sigma) ** 2)
    k /= np.sum(k)
    pad_left = np.full(radius, x[0], dtype=float)
    pad_right = np.full(radius, x[-1], dtype=float)
    padded = np.concatenate([pad_left, x, pad_right])
    return np.convolve(padded, k, mode="valid")
