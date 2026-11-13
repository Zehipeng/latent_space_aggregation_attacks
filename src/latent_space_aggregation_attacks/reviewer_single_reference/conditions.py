from __future__ import annotations

from dataclasses import asdict, dataclass

from . import MODEL_ORDER, TASK_ORDER, WATERMARK_ORDER


@dataclass(frozen=True)
class SingleReferenceCondition:
    task: str
    watermark: str
    model_setting: str
    N_watermarked: int
    N_clean: int
    lambda_pixel: float
    beta: float
    study: str

    @property
    def id(self) -> str:
        fields = asdict(self)
        fields.pop("study")
        return "__".join(f"{key}-{value}" for key, value in fields.items())


def condition_registry() -> list[SingleReferenceCondition]:
    """Build the preregistered one-factor-at-a-time matrix."""
    unique: dict[str, SingleReferenceCondition] = {}

    def add(condition: SingleReferenceCondition) -> None:
        unique.setdefault(condition.id, condition)

    for watermark in WATERMARK_ORDER:
        for model_setting in MODEL_ORDER:
            for task in TASK_ORDER:
                for n_clean in (1, 5, 25):
                    add(SingleReferenceCondition(
                        task, watermark, model_setting, 1, n_clean,
                        20000.0, 1.5, "clean_reference_count",
                    ))
                for lambda_pixel in (10000.0, 20000.0, 50000.0):
                    add(SingleReferenceCondition(
                        task, watermark, model_setting, 1, 5,
                        lambda_pixel, 1.5, "fidelity_weight",
                    ))
                if task == "removal":
                    for beta in (1.0, 1.5, 2.0):
                        add(SingleReferenceCondition(
                            task, watermark, model_setting, 1, 5,
                            20000.0, beta, "removal_strength",
                        ))
    return list(unique.values())


def expected_condition_count() -> int:
    return len(WATERMARK_ORDER) * len(MODEL_ORDER) * (5 + 7)


def validate_registry(conditions: list[SingleReferenceCondition]) -> None:
    if len(conditions) != expected_condition_count():
        raise ValueError(
            f"Expected {expected_condition_count()} single-reference conditions, "
            f"got {len(conditions)}"
        )
    if len({condition.id for condition in conditions}) != len(conditions):
        raise ValueError("Single-reference condition IDs are not unique")
    for condition in conditions:
        if condition.N_watermarked != 1:
            raise ValueError("Every condition must use exactly one watermarked reference")
