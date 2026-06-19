"""ragas 评测共享工具。"""

from __future__ import annotations

from math import isnan
from typing import Iterable


def normalizeMetricValue(value: object) -> float | None:
    """把 ragas 返回的指标值规范为可序列化数字。"""

    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        normalizedValue = float(value)
        if isnan(normalizedValue):
            return None
        return normalizedValue
    raise TypeError(f"不支持的指标值类型: {type(value)!r}")


def safeMean(values: Iterable[object]) -> float | None:
    """对指标列执行忽略空值的平均，避免单条失败污染整体结果。"""

    normalizedValues = [
        value for value in (normalizeMetricValue(item) for item in values) if value is not None
    ]
    if not normalizedValues:
        return None
    return sum(normalizedValues) / len(normalizedValues)
