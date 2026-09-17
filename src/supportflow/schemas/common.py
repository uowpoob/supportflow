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

    两个都不能省：
    1. **必须带 Z**：数据库里存的是 UTC（`utc_now()` 摘掉了 tzinfo），直接序列化
       会得到 `"2026-09-16T10:53:00"` 这种不带时区的串，浏览器按本地时区解析 → 差 8 小时。
    2. **小数秒截到毫秒**：数据库精度是微秒（`DATETIME(6)`），原样输出是 6 位小数秒。
       ECMAScript 的日期格式只认 3 位，V8 会宽容地截断，**Safari 直接返回 Invalid Date**。
       前端虽然有兜底（解析失败就显示原文），但没理由让它去走那条路。
    """
    return (
        value.replace(tzinfo=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _iso_utc_or_null(value: datetime | None) -> str | None:
    return None if value is None else _iso_utc(value)


# 用法：`created_at: UtcInstant` / `paid_at: UtcInstantOrNull`。
# 这是个 `Annotated` 别名，不是类 —— 字段上写它，Pydantic 就知道该用哪个序列化器。
UtcInstant = Annotated[datetime, PlainSerializer(_iso_utc, return_type=str)]
UtcInstantOrNull = Annotated[
    datetime | None, PlainSerializer(_iso_utc_or_null, return_type=str | None)
]
