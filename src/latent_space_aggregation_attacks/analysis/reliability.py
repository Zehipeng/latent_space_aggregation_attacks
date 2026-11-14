from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
from scipy.stats import norm


THRESHOLDS = {
    "tree_ring": 0.05,
    "ringid": 0.05,
    "gaussian_shading": 0.6484375,
}

CONTINUOUS_METRICS = (
    "lpips",
    "ssim",
    "psnr",
    "l2",
    "linf",
    "attack_compute_time",
    "initial_score",
    "final_score",
    "score_change",
    "initial_acceptance_margin",
    "final_acceptance_margin",
    "final_task_margin",
)

PAIRED_METRICS = (
    "success",
    "lpips",
    "ssim",
    "psnr",
    "l2",
    "linf",
    "final_task_margin",
    "score_change",
)

PAIRED_OUTPUT_FIELDS = (
    "comparison", "source_label", "task", "watermark", "model_setting",
    "metric", "left_condition_id", "right_condition_id", "left_method",
    "right_method", "paired_n", "left_mean", "right_mean",
    "mean_paired_difference_left_minus_right", "paired_difference_CI_low",
    "paired_difference_CI_high", "standardized_paired_effect_dz",
    "confidence_level", "bootstrap_replicates",
)


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no", ""}:
        return False
    raise ValueError(f"Not a boolean value: {value!r}")


def optional_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _first(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() != "":
            return value
    return ""


def normalize_row(row: dict[str, Any], source_label: str) -> dict[str, Any]:
    watermark = str(row["watermark"])
    task = str(row["task"])
    threshold = optional_float(row.get("threshold"))
    if threshold is None:
        threshold = THRESHOLDS[watermark]
    initial_score = float(row["initial_score"])
    final_score = float(row["final_score"])
    if watermark == "gaussian_shading":
        initial_acceptance = initial_score - threshold
        final_acceptance = final_score - threshold
    else:
        initial_acceptance = threshold - initial_score
        final_acceptance = threshold - final_score
    task_margin = final_acceptance if task == "forgery" else -final_acceptance
    normalized: dict[str, Any] = {
        "source_label": source_label,
        "protocol_version": row.get("protocol_version", ""),
        "run_id": row.get("run_id", ""),
        "condition_id": row["condition_id"],
        "task": task,
        "watermark": watermark,
        "model_setting": row["model_setting"],
        "method": row.get("method") or "single_reference",
        "key_id": row["key_id"],
        "N": _first(row, "N", "N_watermarked"),
        "N_clean": _first(row, "N_clean"),
        "lambda_pixel": _first(row, "lambda_pixel", "lambda"),
        "beta": _first(row, "beta"),
        "gamma": _first(row, "gamma"),
        "eligible": parse_bool(row["eligible"]),
        "success": parse_bool(row["success"]),
        "initial_score": initial_score,
        "final_score": final_score,
        "score_change": optional_float(row.get("score_change"))
        if row.get("score_change") not in {None, ""}
        else final_score - initial_score,
        "threshold": threshold,
        "initial_acceptance_margin": optional_float(
            row.get("initial_acceptance_margin")
        )
        if row.get("initial_acceptance_margin") not in {None, ""}
        else initial_acceptance,
        "final_acceptance_margin": optional_float(
            row.get("final_acceptance_margin")
        )
        if row.get("final_acceptance_margin") not in {None, ""}
        else final_acceptance,
        "final_task_margin": optional_float(row.get("final_task_margin"))
        if row.get("final_task_margin") not in {None, ""}
        else task_margin,
    }
    for metric in ("lpips", "ssim", "psnr", "l2", "linf"):
        normalized[metric] = optional_float(row.get(metric))
    normalized["attack_compute_time"] = optional_float(
        _first(row, "attack_compute_time", "optimization_compute_time")
    )
    return normalized


def wilson_interval(
    successes: int, sample_n: int, confidence: float = 0.95,
) -> tuple[float, float]:
    if sample_n <= 0:
        return math.nan, math.nan
    z = float(norm.ppf(1 - (1 - confidence) / 2))
    p = successes / sample_n
    denominator = 1 + z * z / sample_n
    center = (p + z * z / (2 * sample_n)) / denominator
    radius = z * math.sqrt(
        p * (1 - p) / sample_n + z * z / (4 * sample_n * sample_n)
    ) / denominator
    low = 0.0 if successes == 0 else max(0.0, center - radius)
    high = 1.0 if successes == sample_n else min(1.0, center + radius)
    return low, high


def _seed(master_seed: int, identity: str) -> int:
    digest = hashlib.sha256(f"{master_seed}|{identity}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def bootstrap_mean_interval(
    values: np.ndarray,
    *,
    replicates: int,
    confidence: float,
    seed: int,
) -> tuple[float, float]:
    clean = np.asarray(values, dtype=np.float64)
    clean = clean[np.isfinite(clean)]
    if clean.size == 0:
        return math.nan, math.nan
    if clean.size == 1 or replicates <= 0:
        value = float(clean[0])
        return value, value
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, clean.size, size=(replicates, clean.size))
    means = clean[indices].mean(axis=1)
    alpha = (1 - confidence) / 2
    low, high = np.quantile(means, [alpha, 1 - alpha])
    return float(low), float(high)


def _identity_fields(first: dict[str, Any]) -> dict[str, Any]:
    return {
        key: first[key]
        for key in (
            "source_label", "protocol_version", "run_id", "condition_id",
            "task", "watermark", "model_setting", "method", "N", "N_clean",
            "lambda_pixel", "beta", "gamma",
        )
    }


def summarize_conditions(
    rows: Iterable[dict[str, Any]],
    *,
    bootstrap_replicates: int = 2000,
    confidence: float = 0.95,
    master_seed: int = 205,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["source_label"]), str(row["condition_id"]))].append(row)
    output: list[dict[str, Any]] = []
    for index, ((_, condition_id), group) in enumerate(sorted(grouped.items())):
        first = group[0]
        eligible = [row for row in group if row["eligible"]]
        successes = sum(bool(row["success"]) for row in eligible)
        low, high = wilson_interval(successes, len(eligible), confidence)
        record = {
            **_identity_fields(first),
            "total_n": len(group),
            "eligible_n": len(eligible),
            "success_n": successes,
            "ASR": successes / len(eligible) if eligible else "",
            "ASR_CI_low": low if eligible else "",
            "ASR_CI_high": high if eligible else "",
            "ASR_CI_method": "Wilson",
            "confidence_level": confidence,
            "bootstrap_replicates": bootstrap_replicates,
        }
        for metric in CONTINUOUS_METRICS:
            values = np.asarray([
                row[metric] for row in group if row.get(metric) is not None
            ], dtype=np.float64)
            prefix = metric
            if values.size == 0:
                record.update({
                    f"{prefix}_n": 0,
                    f"{prefix}_mean": "",
                    f"{prefix}_std": "",
                    f"{prefix}_CI_low": "",
                    f"{prefix}_CI_high": "",
                })
                continue
            metric_low, metric_high = bootstrap_mean_interval(
                values,
                replicates=bootstrap_replicates,
                confidence=confidence,
                seed=_seed(master_seed + index, f"{condition_id}|{metric}"),
            )
            record.update({
                f"{prefix}_n": int(values.size),
                f"{prefix}_mean": float(values.mean()),
                f"{prefix}_std": float(values.std(ddof=1))
                if values.size > 1 else 0.0,
                f"{prefix}_CI_low": metric_low,
                f"{prefix}_CI_high": metric_high,
            })
        output.append(record)
    return output


@dataclass(frozen=True)
class Comparison:
    name: str
    source_label: str
    left_condition_id: str
    right_condition_id: str


def _float_or_blank(value: Any) -> float | None:
    return optional_float(value)


def planned_comparisons(rows: Iterable[dict[str, Any]]) -> list[Comparison]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["source_label"]), str(row["condition_id"]))].append(row)
    conditions = {identity: values[0] for identity, values in groups.items()}
    comparisons: set[Comparison] = set()

    for (source_label, condition_id) in conditions:
        prefix = "e7_matched_noise_of__"
        if condition_id.startswith(prefix):
            parent = condition_id[len(prefix):]
            if (source_label, parent) in conditions:
                comparisons.add(Comparison(
                    "parent_vs_exact_matched_noise", source_label,
                    parent, condition_id,
                ))

    by_signature: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for condition in conditions.values():
        signature = (
            condition["source_label"], condition["task"], condition["watermark"],
            condition["model_setting"], _float_or_blank(condition["lambda_pixel"]),
        )
        by_signature[signature].append(condition)
    for candidates in by_signature.values():
        proposed = [
            row for row in candidates
            if row["method"] == "proposed" and str(row["N"]) == "1"
            and (row["task"] == "forgery" or _float_or_blank(row["beta"]) == 1.5)
        ]
        jain = [
            row for row in candidates
            if row["method"] == "jain" and str(row["N"]) == "1"
        ]
        for left in proposed:
            for right in jain:
                comparisons.add(Comparison(
                    "proposed_vs_jain_N1", left["source_label"],
                    left["condition_id"], right["condition_id"],
                ))

    simple_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for condition in conditions.values():
        signature = (
            condition["source_label"], condition["task"], condition["watermark"],
            condition["model_setting"], str(condition["N"]),
        )
        simple_groups[signature].append(condition)
    for candidates in simple_groups.values():
        proposed = [
            row for row in candidates
            if row["method"] == "proposed"
            and _float_or_blank(row["lambda_pixel"]) == 20000.0
            and (row["task"] == "forgery" or _float_or_blank(row["beta"]) == 1.5)
        ]
        simple = [
            row for row in candidates
            if row["method"] == "simple_averaging"
            and _float_or_blank(row["gamma"]) == 1.0
        ]
        for left in proposed:
            for right in simple:
                comparisons.add(Comparison(
                    "proposed_main_vs_simple_averaging",
                    left["source_label"],
                    left["condition_id"], right["condition_id"],
                ))
    return sorted(comparisons, key=lambda item: (
        item.name, item.source_label, item.left_condition_id, item.right_condition_id,
    ))


def paired_comparison_rows(
    rows: Iterable[dict[str, Any]],
    *,
    bootstrap_replicates: int = 5000,
    confidence: float = 0.95,
    master_seed: int = 205,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    row_list = list(rows)
    for row in row_list:
        groups[(str(row["source_label"]), str(row["condition_id"]))][
            str(row["key_id"])
        ] = row
    output: list[dict[str, Any]] = []
    for comparison_index, comparison in enumerate(planned_comparisons(row_list)):
        left = groups[(comparison.source_label, comparison.left_condition_id)]
        right = groups[(comparison.source_label, comparison.right_condition_id)]
        common = sorted(set(left) & set(right))
        if not common:
            continue
        left_first = left[common[0]]
        right_first = right[common[0]]
        for metric in PAIRED_METRICS:
            pairs: list[tuple[float, float]] = []
            for key_id in common:
                left_row, right_row = left[key_id], right[key_id]
                if metric == "success":
                    if not (left_row["eligible"] and right_row["eligible"]):
                        continue
                    pairs.append((float(left_row[metric]), float(right_row[metric])))
                else:
                    left_value = left_row.get(metric)
                    right_value = right_row.get(metric)
                    if left_value is None or right_value is None:
                        continue
                    pairs.append((float(left_value), float(right_value)))
            if not pairs:
                continue
            array = np.asarray(pairs, dtype=np.float64)
            differences = array[:, 0] - array[:, 1]
            low, high = bootstrap_mean_interval(
                differences,
                replicates=bootstrap_replicates,
                confidence=confidence,
                seed=_seed(
                    master_seed + comparison_index,
                    f"{comparison.left_condition_id}|{comparison.right_condition_id}|{metric}",
                ),
            )
            std = float(differences.std(ddof=1)) if differences.size > 1 else 0.0
            output.append({
                "comparison": comparison.name,
                "source_label": left_first["source_label"],
                "task": left_first["task"],
                "watermark": left_first["watermark"],
                "model_setting": left_first["model_setting"],
                "metric": metric,
                "left_condition_id": comparison.left_condition_id,
                "right_condition_id": comparison.right_condition_id,
                "left_method": left_first["method"],
                "right_method": right_first["method"],
                "paired_n": int(differences.size),
                "left_mean": float(array[:, 0].mean()),
                "right_mean": float(array[:, 1].mean()),
                "mean_paired_difference_left_minus_right": float(differences.mean()),
                "paired_difference_CI_low": low,
                "paired_difference_CI_high": high,
                "standardized_paired_effect_dz": (
                    float(differences.mean() / std) if std > 0 else ""
                ),
                "confidence_level": confidence,
                "bootstrap_replicates": bootstrap_replicates,
            })
    return output


def detection_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = (
        "source_label", "protocol_version", "run_id", "condition_id", "task",
        "watermark", "model_setting", "method", "key_id", "N", "N_clean",
        "lambda_pixel", "beta", "gamma", "eligible", "success", "threshold",
        "initial_score", "final_score", "score_change",
        "initial_acceptance_margin", "final_acceptance_margin", "final_task_margin",
    )
    return [{key: row[key] for key in fields} for row in rows]
