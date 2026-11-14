from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Callable

import numpy as np


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0 or successes < 0 or successes > total:
        raise ValueError("invalid binomial counts")
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denominator
    radius = z * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total)) / denominator
    low = 0.0 if successes == 0 else max(0.0, centre - radius)
    high = 1.0 if successes == total else min(1.0, centre + radius)
    return low, high


def rankdata(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2.0 + 1.0
        start = end
    return ranks


def spearman(first: list[float] | np.ndarray, second: list[float] | np.ndarray) -> float:
    a, b = np.asarray(first, dtype=np.float64), np.asarray(second, dtype=np.float64)
    if len(a) != len(b) or len(a) < 2:
        return float("nan")
    ra, rb = rankdata(a), rankdata(b)
    if np.std(ra) == 0 or np.std(rb) == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def clustered_spearman_ci(
    rows: list[dict[str, Any]], x: str, y: str, *, seed: int,
    replicates: int = 2000,
) -> tuple[float, float, float, int]:
    usable = [
        row for row in rows
        if row.get(x) not in {None, ""} and row.get(y) not in {None, ""}
    ]
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in usable:
        by_key[str(row["key_id"])].append(row)
    keys = sorted(by_key)
    estimate = spearman(
        [float(row[x]) for row in usable], [float(row[y]) for row in usable],
    )
    if len(keys) < 2:
        return estimate, float("nan"), float("nan"), len(keys)
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(replicates):
        sampled = rng.choice(keys, size=len(keys), replace=True)
        chosen = [row for key in sampled for row in by_key[str(key)]]
        value = spearman(
            [float(row[x]) for row in chosen],
            [float(row[y]) for row in chosen],
        )
        if math.isfinite(value):
            values.append(value)
    if not values:
        return estimate, float("nan"), float("nan"), len(keys)
    low, high = np.quantile(np.asarray(values), [0.025, 0.975])
    return estimate, float(low), float(high), len(keys)


def paired_strategy_differences(
    rows: list[dict[str, Any]], *, strategy_a: str, strategy_b: str,
    metric: str, transform: Callable[[dict[str, Any]], float] | None = None,
    seed: int = 0, replicates: int = 5000,
) -> dict[str, Any]:
    convert = transform or (lambda row: float(row[metric]))
    first = {str(row["key_id"]): convert(row) for row in rows if row["selection_strategy"] == strategy_a}
    second = {str(row["key_id"]): convert(row) for row in rows if row["selection_strategy"] == strategy_b}
    keys = sorted(set(first) & set(second))
    if not keys:
        raise ValueError("paired comparison has no common keys")
    differences = np.asarray([first[key] - second[key] for key in keys], dtype=np.float64)
    rng = np.random.default_rng(seed)
    sampled = rng.choice(differences, size=(replicates, len(differences)), replace=True)
    low, high = np.quantile(sampled.mean(axis=1), [0.025, 0.975])
    return {
        "strategy_a": strategy_a, "strategy_b": strategy_b,
        "metric": metric, "paired_n": len(keys),
        "mean_difference_a_minus_b": float(differences.mean()),
        "ci95_low": float(low), "ci95_high": float(high),
    }
