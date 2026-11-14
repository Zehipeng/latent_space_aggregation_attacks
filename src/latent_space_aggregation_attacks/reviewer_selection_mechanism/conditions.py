from __future__ import annotations

from dataclasses import asdict, dataclass

from . import MODEL_ORDER, TASK_ORDER, WATERMARK_ORDER
from .strategies import strategy_registry


@dataclass(frozen=True)
class SelectionCondition:
    task: str
    watermark: str
    model_setting: str
    selection_strategy: str
    N_watermarked: int = 25
    N_clean: int = 5
    lambda_pixel: float = 20000.0
    beta: float = 1.5

    @property
    def id(self) -> str:
        return "__".join(f"{key}-{value}" for key, value in asdict(self).items())


def condition_registry() -> list[SelectionCondition]:
    return [
        SelectionCondition(task, watermark, model_setting, strategy.id)
        for strategy in strategy_registry()
        for model_setting in MODEL_ORDER
        for watermark in WATERMARK_ORDER
        for task in TASK_ORDER
    ]


def validate_registry(conditions: list[SelectionCondition]) -> None:
    expected = 4 * len(MODEL_ORDER) * len(WATERMARK_ORDER) * len(TASK_ORDER)
    if len(conditions) != expected:
        raise ValueError(f"expected {expected} E2 conditions, got {len(conditions)}")
    if len({condition.id for condition in conditions}) != len(conditions):
        raise ValueError("E2 condition IDs are not unique")
    for condition in conditions:
        if (
            condition.N_watermarked != 25
            or condition.N_clean != 5
            or condition.lambda_pixel != 20000.0
            or condition.beta != 1.5
        ):
            raise ValueError("E2 main attack settings changed")
