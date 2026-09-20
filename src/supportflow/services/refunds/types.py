"""退款领域的**类型与不变量**：常量、判定结果。

这里没有任何函数逻辑，只有"长什么样"。分出来的理由很实际：
`schemas/refunds/` 要用 `Eligibility` 把 ORM 翻成响应，如果它住在 `eligibility.py` 里，
schema 层就得为了拿一个类型去 import 业务逻辑模块 —— 类型不该跟行为绑在一起。

`RefundRequestRow` / `RefundRequestView` 已经搬到 `repository/refund/types.py`
（它们描述的是"查询返回什么"，属于数据访问层）。这里重新导出一遍，
`from supportflow.services.refunds.types import RefundRequestView` 这种老写法照旧可用。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from supportflow.models.enums import RefundStatus
from supportflow.repository.refund.types import RefundRequestRow, RefundRequestView

# 演示政策 demo-refund-v1：签收后 0～14 天（含边界）可申请整单退款。
# 天数只在这里出现一次 —— 判定、文案、前后端提示都引用它。
REFUND_WINDOW_DAYS = 14
REFUND_WINDOW = timedelta(days=REFUND_WINDOW_DAYS)

# "占用订单退款名额"的状态。
# ⚠️ 必须与 `RefundRequest.active_order_id` 那个生成列里的 CASE 逐字一致 ——
# 那是数据库级的并发防线（唯一约束），这里是应用层的判据。两边不一致就会出现
# "应用层说没有有效申请、数据库却拒绝插入"的怪现象。改这里要一起写迁移。
#
# 由调用方传给 `repository/refund/eligibility.py::find_request_in_statuses` ——
# 数据访问层不认识"什么算占名额"，那是规则，住在这一层。
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
