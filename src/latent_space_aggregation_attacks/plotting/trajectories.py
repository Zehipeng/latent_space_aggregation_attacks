from __future__ import annotations

from pathlib import Path
from typing import Iterable

FIGURES = {
    ("forgery", "lambda"): "forgery_lambda_detector_trajectory.png",
    ("forgery", "N"): "forgery_N_detector_trajectory.png",
    ("removal", "lambda"): "removal_lambda_detector_trajectory.png",
    ("removal", "N"): "removal_N_detector_trajectory.png",
    ("removal", "beta"): "removal_beta_detector_trajectory.png",
}


def plot_detector_trajectory(rows: Iterable[dict], task: str, factor: str, output_dir: str | Path, thresholds: dict[str, float]) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    records = list(rows)
    models = ("SDv1.4", "SDv2.0"); watermarks = ("tree_ring", "ringid", "gaussian_shading")
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), squeeze=False)
    for row_index, model in enumerate(models):
        for column_index, watermark in enumerate(watermarks):
            axis = axes[row_index, column_index]
            panel = [r for r in records if r["task"] == task and r["factor_name"] == factor and r["model"] == model and r["watermark"] == watermark]
            values = sorted({str(r["factor_value"]) for r in panel}, key=float)
            if len(values) != 3: raise ValueError("Every panel must contain exactly three factor values")
            colors = ("#1f77b4", "#ff7f0e", "#2ca02c")
            linestyles = ("-", "--", ":")
            for index, value in enumerate(values):
                points = sorted((r for r in panel if str(r["factor_value"]) == value), key=lambda r: int(r["step"]))
                x = [int(r["step"]) for r in points]
                y = [float(r["center"]) for r in points]
                low = [float(r["lower"]) for r in points]; high = [float(r["upper"]) for r in points]
                axis.plot(
                    x, y, marker="o", label=value, color=colors[index],
                    linestyle=linestyles[index],
                )
                axis.fill_between(x, low, high, color=colors[index], alpha=.2)
            axis.axhline(thresholds[watermark], color="black", linestyle="--", linewidth=1)
            axis.set_title(f"{model} / {watermark}"); axis.set_xlabel("Iteration")
            axis.set_ylabel("bit accuracy" if watermark == "gaussian_shading" else "p-value")
            if watermark != "gaussian_shading": axis.set_ylim(0, 1)
            axis.legend(title=factor)
    fig.tight_layout()
    destination = Path(output_dir) / FIGURES[(task, factor)]; destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=300); plt.close(fig)
    return destination
