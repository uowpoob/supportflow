"""退款领域的**类型与不变量**：常量、判定结果、查询行。

这里没有任何函数逻辑，只有"长什么样"。分出来的理由很实际：
`schemas/refunds/` 要用 `Eligibility` / `RefundRequestRow` / `RefundRequestView`
把 ORM 翻成响应，如果这三个 dataclass 住在 `eligibility.py` / `queries.py` 里，
schema 层就得为了拿一个类型去 import 业务逻辑模块 —— 类型不该跟行为绑在一起。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from supportflow.models.entities import Order, RefundApproval, RefundRecord, RefundRequest
from supportflow.models.enums import RefundStatus

# 演示政策 demo-refund-v1：签收后 0～14 天（含边界）可申请整单退款。
# 天数只在这里出现一次 —— 判定、文案、前后端提示都引用它。
REFUND_WINDOW_DAYS = 14
REFUND_WINDOW = timedelta(days=REFUND_WINDOW_DAYS)

# "占用订单退款名额"的状态。
# ⚠️ 必须与 `RefundRequest.active_order_id` 那个生成列里的 CASE 逐字一致 ——
# 那是数据库级的并发防线（唯一约束），这里是应用层的判据。两边不一致就会出现
# "应用层说没有有效申请、数据库却拒绝插入"的怪现象。改这里要一起写迁移。
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


@dataclass(frozen=True)
class RefundRequestRow:
    """列表行：申请本身 + 订单号 [+ 归属信息（仅管理侧）]。

    `user_id` / `username` 是可选的：客户侧列表查的是"我的申请"，
    归属恒等于他自己，带上纯属噪音（也就没必要 join users）。
    """

    request: RefundRequest
    order_no: str
    user_id: int | None = None
    username: str | None = None


@dataclass(frozen=True)
class RefundRequestView:
    """详情：申请 + 订单依据 + 已有审批 + 退款流水。

    四个对象一起给出去，是因为"这条申请该不该批"这个判断需要它们同时在手边：
    订单给出实付与签收时间，审批行说明是否已决策，流水说明是否真的退过钱。
    `approval_admin` 单独留一个字段（而不是塞进 approval）是因为它是 `users`
    表里的名字，管理侧要显示"谁批的" —— 审计信息不能只留一个 admin_id。
    """

    request: RefundRequest
    order: Order
    username: str | None
    approval: RefundApproval | None
    approval_admin: str | None
    record: RefundRecord | None
