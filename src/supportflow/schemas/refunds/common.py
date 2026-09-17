"""客户侧与管理侧**共用**的三个片段：订单摘要、审批结果、退款流水。

放一起是因为它们在两边是同一种东西 —— 管理员和客户看到的是同一条审批、同一笔流水，
只有"谁的申请"这一点不同（那部分留在各自的 `customer.py` / `admin.py` 里）。
复制两份的下场是改一处漏一处，最后两边的字段对不上。
"""

from pydantic import BaseModel

from supportflow.models.entities import Order
from supportflow.models.enums import (
    ApprovalDecision,
    FulfillmentStatus,
    PaymentStatus,
    RefundExecutionStatus,
)
from supportflow.schemas.common import UtcInstant, UtcInstantOrNull
from supportflow.services.refunds.types import RefundRequestView


class RefundOrderBrief(BaseModel):
    """申请所依据的订单快照。

    审批时最关键的就是这几个字段 —— 管理员要一眼看到"实付多少、签收没有、签收多久了"，
    而不是点进订单页再翻一次。这也正好是资格规则用到的那几列。
    """

    order_no: str
    paid_amount_cents: int
    payment_status: PaymentStatus
    fulfillment_status: FulfillmentStatus
    delivered_at: UtcInstantOrNull

    @classmethod
    def from_row(cls, order: Order) -> "RefundOrderBrief":
        return cls(
            order_no=order.order_no,
            paid_amount_cents=order.paid_amount_cents,
            payment_status=order.payment_status,
            fulfillment_status=order.fulfillment_status,
            delivered_at=order.delivered_at,
        )


class RefundApprovalOut(BaseModel):
    """审批结果。

    带上 `request_key` / `order_no`：审批记录页是一张独立的列表，
    不说清楚"批的是哪一条申请、哪一单"，这一行信息就没有意义。
    `admin_username` 是"谁批的"，审计要留名不只留 ID。
    """

    request_key: str
    order_no: str
    decision: ApprovalDecision
    comment: str | None
    admin_username: str | None
    decided_at: UtcInstant

    @classmethod
    def from_row(
        cls, approval, admin_username: str | None, request_key: str, order_no: str
    ) -> "RefundApprovalOut":
        return cls(
            request_key=request_key,
            order_no=order_no,
            decision=approval.decision,
            comment=approval.comment,
            admin_username=admin_username,
            decided_at=approval.created_at,
        )


class RefundRecordOut(BaseModel):
    """模拟退款执行流水。`last_error` 只有失败时才有值。"""

    request_key: str
    order_no: str
    refund_no: str
    amount_cents: int
    status: RefundExecutionStatus
    attempt_count: int
    last_error: str | None
    succeeded_at: UtcInstantOrNull

    @classmethod
    def from_row(cls, record, request_key: str, order_no: str) -> "RefundRecordOut":
        return cls(
            request_key=request_key,
            order_no=order_no,
            refund_no=record.refund_no,
            amount_cents=record.amount_cents,
            status=record.status,
            attempt_count=record.attempt_count,
            last_error=record.last_error,
            succeeded_at=record.succeeded_at,
        )


# ---- 详情里两个可空子块，客户侧/管理侧两个详情类共用一份构造逻辑 ----
#
# 不写成 `RefundApprovalOut` 的类方法，是因为它需要的是整个 `view`
# （申请号、订单号、审批人都在里面），放进审批对象自己的类里会变成
# "一个对象知道怎么构造另一个对象"的怪圈。


def _approval_of(view: RefundRequestView) -> RefundApprovalOut | None:
    """审批块；没被决策过就是 None（"还没批"和"批了"在界面上是两回事）。"""
    if view.approval is None:
        return None
    return RefundApprovalOut.from_row(
        view.approval, view.approval_admin, view.request.request_key, view.order.order_no
    )


def _record_of(view: RefundRequestView) -> RefundRecordOut | None:
    """退款流水；没退过款就是 None。"""
    if view.record is None:
        return None
    return RefundRecordOut.from_row(
        view.record, view.request.request_key, view.order.order_no
    )
