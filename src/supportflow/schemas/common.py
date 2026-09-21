"""跨业务公用的结构片段。

这里只放**被两个以上业务用到**的东西。目前只有时间类型 —— 订单、退款、
以后的会话与审批记录，时间字段的序列化方式必须完全一致，各写一份迟早分叉。

（原来它住在 `orders.py` 里，退款接口要从订单模块 import 时间类型，
方向就不太对：退款不是订单的下级。挪出来之后两边都从 `common` 取。）
"""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def _iso_utc(value: datetime) -> str:
    """UTC 无时区时间 → 带 Z 的 ISO 字符串。

    """
    return (
        value.replace(tzinfo=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _iso_utc_or_null(value: datetime | None) -> str | None:
    return None if value is None else _iso_utc(value)


# 用法：`created_at: UtcInstant` / `paid_at: UtcInstantOrNull`。
UtcInstant = Annotated[datetime, PlainSerializer(_iso_utc, return_type=str)]
UtcInstantOrNull = Annotated[
    datetime | None, PlainSerializer(_iso_utc_or_null, return_type=str | None)
]
