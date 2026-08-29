from __future__ import annotations

TABLE_COLUMNS = {
    "lambda": ["Watermark", "Model", "lambda", "ASR", "l2", "linf", "LPIPS", "SSIM", "PSNR", "FID", "Time"],
    "N": ["Watermark", "Model", "N", "ASR", "l2", "linf", "LPIPS", "SSIM", "PSNR", "FID", "Time"],
    "method": ["Watermark", "Model", "Method", "ASR", "l2", "linf", "LPIPS", "SSIM", "PSNR", "FID", "Time"],
    "beta": ["Watermark", "Model", "beta", "ASR", "l2", "linf", "LPIPS", "SSIM", "PSNR", "FID", "Time"],
}


def validate_table_columns(kind: str, columns: list[str]) -> None:
    if columns != TABLE_COLUMNS[kind]:
        raise ValueError(f"Invalid {kind} table columns")

