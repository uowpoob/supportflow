"""管理侧：审批入参、申请列表、申请详情、分页信封。

管理侧的对象比客户侧多一层**归属**（`user_id` / `username`）—— 管理员看的是
所有人的申请，必须知道"是哪一位的"。审批人身份则永远取自服务端会话，
接口上没有任何地方能传 `admin_id`，跟客户侧不传 `user_id` 是同一条硬边界。
"""

from pydantic import BaseModel, Field, field_validator

from supportflow.models.enums import ApprovalDecision, RefundStatus
from supportflow.schemas.common import UtcInstant
from supportflow.schemas.refunds.common import (
    RefundApprovalOut,
    RefundOrderBrief,
    RefundRecordOut,
    _approval_of,
    _record_of,
)
from supportflow.schemas.refunds.customer import RefundRequestBrief
from supportflow.services.refunds.types import RefundRequestRow, RefundRequestView

class RefundDecisionIn(BaseModel):
    """管理员审批。

    `decision` 直接复用 `ApprovalDecision` 枚举（`approved` / `rejected`），
    """

    decision: ApprovalDecision
    comment: str | None = Field(default=None, max_length=1000, description="审批意见")

    @field_validator("comment")
    @classmethod
    def _blank_comment_to_none(cls, value: str | None) -> str | None:
        """空字符串统一存成 NULL，避免库里同时出现 `''` 和 `NULL` 两种"没写"。"""
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

class AdminRefundRequestBrief(RefundRequestBrief):
    """管理侧列表行：在客户侧那五个字段之上，多出**归属**信息。"""

    user_id: int
    username: str

    @classmethod
    def from_row(cls, row: RefundRequestRow) -> "AdminRefundRequestBrief":
        assert row.username is not None and row.user_id is not None  # 管理侧查询一定会 join 出来
        return cls(
            request_key=row.request.request_key,
            order_no=row.order_no,
            amount_cents=row.request.amount_cents,
            status=row.request.status,
            created_at=row.request.created_at,
            user_id=row.user_id,
            username=row.username,
        )


class AdminRefundRequestDetail(AdminRefundRequestBrief):
    """管理侧详情 = 列表行 + 原因原文 + 订单依据 + 审批 + 流水。"""

    reason_original: str
    reason_category: str | None
    updated_at: UtcInstant
    order: RefundOrderBrief
    approval: RefundApprovalOut | None
    refund_record: RefundRecordOut | None

    @classmethod
    def from_view(cls, view: RefundRequestView) -> "AdminRefundRequestDetail":
        request = view.request
        assert view.username is not None
        return cls(
            request_key=request.request_key,
            order_no=view.order.order_no,
            amount_cents=request.amount_cents,
            status=request.status,
            created_at=request.created_at,
            user_id=view.order.user_id,
            username=view.username,
            reason_original=request.reason_original,
            reason_category=request.reason_category,
            updated_at=request.updated_at,
            order=RefundOrderBrief.from_row(view.order),
            approval=_approval_of(view),
            refund_record=_record_of(view),
        )

class AdminRefundRequestPage(BaseModel):
    items: list[AdminRefundRequestBrief]
    total: int
    offset: int
    limit: int


class RefundApprovalPage(BaseModel):
    items: list[RefundApprovalOut]
    total: int
    offset: int
    limit: int


class RefundRecordPage(BaseModel):
    items: list[RefundRecordOut]
    total: int
    offset: int
    limit: int
