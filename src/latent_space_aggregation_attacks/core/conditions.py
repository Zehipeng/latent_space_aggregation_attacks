from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class Condition:
    experiment: str
    task: str
    watermark: str
    model_setting: str
    method: str
    N: int | None = None
    lambda_pixel: float | None = None
    beta: float | None = None
    gamma: float | None = None
    transform: str | None = None

    @property
    def id(self) -> str:
        fields = asdict(self)
        # Experiment labels are reporting views, not part of an output identity.
        # This makes E1/E2 main settings reusable by E3/E4/E5.
        fields.pop("experiment")
        return "__".join(f"{key}-{value}" for key, value in fields.items() if value is not None)


def formal_condition_registry() -> list[Condition]:
    watermarks = ("tree_ring", "ringid", "gaussian_shading")
    models = ("same_model_sd14_target_sd14_vae_proxy", "cross_model_sd2_target_sd14_vae_proxy")
    tasks = ("forgery", "removal")
    unique: dict[str, Condition] = {}
    def add(condition: Condition) -> None:
        unique.setdefault(condition.id, condition)
    for watermark in watermarks:
        for model in models:
            for task in tasks:
                add(Condition("E1" if task == "forgery" else "E2", task, watermark, model, "jain", 1, 10000.0))
                add(Condition("E1" if task == "forgery" else "E2", task, watermark, model, "simple_averaging", 5, gamma=1.0))
                add(Condition("E1" if task == "forgery" else "E2", task, watermark, model, "proposed", 5, 10000.0, 1.5 if task == "removal" else None))
                for lam in (10000.0, 20000.0, 50000.0):
                    for method in ("jain", "proposed"):
                        add(Condition("E3", task, watermark, model, method, 1 if method == "jain" else 5, lam, 1.5 if task == "removal" and method == "proposed" else None))
                for n in (1, 5, 25):
                    add(Condition("E4", task, watermark, model, "proposed", n, 10000.0, 1.5 if task == "removal" else None))
                    add(Condition("E4", task, watermark, model, "simple_averaging", n, gamma=1.0))
            for beta in (1.0, 1.5, 2.0):
                add(Condition("E5", "removal", watermark, model, "proposed", 5, 10000.0, beta))
            for transform in ("jpeg25", "crop75", "resize384", "gaussian_blur8", "gaussian_noise01"):
                add(Condition("E6", "removal", watermark, model, "distortion", transform=transform))
    return list(unique.values())


def conditions_for_task(task: str) -> list[Condition]:
    if task not in {"forgery", "removal"}:
        raise ValueError(f"Unsupported formal task: {task}")
    return [condition for condition in formal_condition_registry() if condition.task == task]


def expected_output_counts(*, key_count: int = 200, task: str | None = None) -> dict[str, int]:
    conditions = formal_condition_registry()
    if task is not None:
        conditions = [condition for condition in conditions if condition.task == task]
    iterative = sum(condition.method in {"jain", "proposed"} for condition in conditions)
    return {
        "formal_unique_outputs": len(conditions) * key_count,
        "iterative_outputs": iterative * key_count,
        "p0_online_units": 0,
        "p0_confirmation_units": 0,
    }


def validate_registry_scale(conditions: list[Condition]) -> None:
    if len(conditions) != 174:
        raise ValueError(f"Expected 174 unique 200-key conditions, got {len(conditions)}")
    iterative = sum(condition.method in {"jain", "proposed"} for condition in conditions)
    if iterative != 108:
        raise ValueError(f"Expected 108 iterative conditions, got {iterative}")


def expand_units(conditions: Iterable[Condition], key_count: int) -> int:
    return sum(1 for _ in conditions) * key_count
