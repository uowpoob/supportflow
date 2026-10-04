"""退款领域的：常量、判定结果。

"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from supportflow.models.enums import RefundStatus
from supportflow.repository.refund.types import RefundRequestRow, RefundRequestView

# 演示政策 demo-refund-v1：签收后 0～14 天（含边界）可申请整单退款。
# 天数只在这里出现一次 —— 判定、文案、前后端提示都引用它。
REFUND_WINDOW_DAYS = 14
REFUND_WINDOW = timedelta(days=REFUND_WINDOW_DAYS)

# ⚠️ "占用订单退款名额"的状态：必须与 `RefundRequest.active_order_id` 生成列的 CASE 逐字一致
# （数据库唯一约束防线 vs 应用层判据）；两边不一致会出现"应用层放行、数据库却拒绝插入"，改这里要同步写迁移。
ACTIVE_REQUEST_STATUSES: tuple[RefundStatus, ...] = (
    RefundStatus.PENDING,
    RefundStatus.APPROVED,
    RefundStatus.REFUNDED,
)


@dataclass(frozen=True)
class Eligibility:
    """一次资格判定的结果。纯数据，不绑定 ORM 对象。

    `code` 是给程序看的稳定标识（前端按它决定按钮状态），`message` 是给人看的
    一句话解释。两者都要有：只给文案的话前端没法判断"该不该禁用按钮"，
    只给 code 的话用户不知道为什么不能退。
    """

    eligible: bool
    code: str
    message: str
    amount_cents: int
    delivered_at: datetime | None
    window_ends_at: datetime | None
    existing_request_key: str | None = None


__all__ = [
    "ACTIVE_REQUEST_STATUSES",
    "REFUND_WINDOW",
    "REFUND_WINDOW_DAYS",
    "Eligibility",
    "RefundRequestRow",
    "RefundRequestView",
]
