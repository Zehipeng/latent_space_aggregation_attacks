from __future__ import annotations

import math
from typing import Iterable

import numpy as np
from scipy import stats


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0 or not 0 <= successes <= n:
        raise ValueError("Invalid binomial counts")
    p = successes / n
    denominator = 1 + z*z/n
    center = (p + z*z/(2*n)) / denominator
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denominator
    return center - half, center + half


def mcnemar_exact(first: Iterable[bool], second: Iterable[bool]) -> dict[str, float | int]:
    pairs = list(zip(first, second))
    b = sum(a and not c for a, c in pairs)
    c = sum((not a) and c for a, c in pairs)
    p = float(stats.binomtest(min(b, c), b + c, 0.5).pvalue) if b + c else 1.0
    return {"first_only": b, "second_only": c, "p_value": p}


def paired_wilcoxon(first: Iterable[float], second: Iterable[float]) -> dict[str, float]:
    a, b = np.asarray(list(first), dtype=float), np.asarray(list(second), dtype=float)
    if a.shape != b.shape or not len(a):
        raise ValueError("Paired samples must be nonempty and equal length")
    differences = b - a
    p = 1.0 if np.allclose(differences, 0) else float(stats.wilcoxon(differences, alternative="two-sided").pvalue)
    return {"median_paired_difference": float(np.median(differences)), "p_value": p}


def holm_adjust(p_values: Iterable[float]) -> list[float]:
    values = list(map(float, p_values)); count = len(values)
    order = sorted(range(count), key=values.__getitem__)
    adjusted = [0.0] * count; running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (count - rank) * values[index]))
        adjusted[index] = running
    return adjusted


def bootstrap_ci(values: Iterable[float], *, seed: int, samples: int = 10000) -> tuple[float, float]:
    array = np.asarray(list(values), dtype=float)
    if not len(array): raise ValueError("No values")
    rng = np.random.default_rng(seed)
    means = np.mean(rng.choice(array, size=(samples, len(array)), replace=True), axis=1)
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))

