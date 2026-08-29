from __future__ import annotations


def accepted(watermark: str, score: float, threshold: float) -> bool:
    if watermark in {"tree_ring", "ringid"}:
        return score <= threshold
    if watermark == "gaussian_shading":
        return score >= threshold
    raise ValueError(watermark)


def success(task: str, watermark: str, before: float, after: float, threshold: float) -> tuple[bool, bool, bool]:
    before_accepted = accepted(watermark, before, threshold)
    after_accepted = accepted(watermark, after, threshold)
    if task == "forgery":
        eligible = not before_accepted
        succeeded = eligible and after_accepted
    elif task == "removal":
        eligible = before_accepted
        if watermark in {"tree_ring", "ringid"}:
            # Protocol intentionally treats equality as removal success.
            succeeded = eligible and after >= threshold
        else:
            succeeded = eligible and not after_accepted
    else:
        raise ValueError(task)
    return eligible, succeeded, after_accepted

