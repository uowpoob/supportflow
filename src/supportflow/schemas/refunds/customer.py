"""客户侧：提交申请、我的申请列表、我的申请详情、分页信封。

客户侧的对象里**没有** `user_id` / `username` —— 这条申请本来就是他的。
那份归属信息只在管理侧有意义，见 `admin.py`。
"""

from pydantic import BaseModel, Field, field_validator

from supportflow.models.enums import RefundStatus
from supportflow.schemas.common import UtcInstant
from supportflow.schemas.refunds.common import (
    RefundApprovalOut,
    RefundOrderBrief,
    RefundRecordOut,
    _approval_of,
    _record_of,
)
from supportflow.services.refunds.types import RefundRequestRow, RefundRequestView

# ------------------------------- 请求 -------------------------------


class RefundRequestCreate(BaseModel):
    """提交退款申请。

    ⚠️ 刻意**没有** `amount_cents` 字段。金额固定取数据库里的实付金额 ——
    一旦这个字段存在，就一定会有人（包括模型）往里填数，而"退款金额由客户端决定"
    是个不能补的洞。同理也没有 `user_id`：身份只从 Cookie 来。
    """

    order_no: str = Field(min_length=1, max_length=64, description="要退款的订单号")
    reason: str = Field(
        min_length=1,
        max_length=1000,
        description="客户填写的退款原因原文，原样保存，不做加工",
    )
    conversation_id: str | None = Field(
        default=None,
        max_length=36,
        description="该申请所属的对话；网页表单不传，由服务端新开一条会话",
    )

    @field_validator("reason")
    @classmethod
    def _reject_blank_reason(cls, value: str) -> str:
        """全空白不算理由。

        数据库上还有 `length(trim(reason_original)) > 0` 兜着，但那会变成 500；
        在这里拦下来是 422，前端能直接告诉用户"原因不能为空"。
        """
        stripped = value.strip()
        if not stripped:
            raise ValueError("退款原因不能为空或只有空白字符")
        return stripped


# ------------------------------- 列表与详情 -------------------------------


class RefundRequestBrief(BaseModel):
    """客户侧列表行。没有 `user_id` / `username` —— 这条申请本来就是他的。"""

    request_key: str
    order_no: str
    amount_cents: int
    status: RefundStatus
    created_at: UtcInstant

    @classmethod
    def from_row(cls, row: RefundRequestRow) -> "RefundRequestBrief":
        return cls(
            request_key=row.request.request_key,
            order_no=row.order_no,
            amount_cents=row.request.amount_cents,
            status=row.request.status,
            created_at=row.request.created_at,
        )


class MyRefundRequestDetail(RefundRequestBrief):
    """客户侧详情 = 列表行 + 原因原文 + 订单依据 + 审批意见 + 退款结果。

    `reason_original` 给的是**原文**，不是分类结果 —— 客户看到的应该是他写的话。
    分类（`reason_category`）留给后端和模型用。
    """

    reason_original: str
    reason_category: str | None
    updated_at: UtcInstant
    order: RefundOrderBrief
    approval: RefundApprovalOut | None
    refund_record: RefundRecordOut | None

    @classmethod
    def from_view(cls, view: RefundRequestView) -> "MyRefundRequestDetail":
        request = view.request
        return cls(
            request_key=request.request_key,
            order_no=view.order.order_no,
            amount_cents=request.amount_cents,
            status=request.status,
            created_at=request.created_at,
            reason_original=request.reason_original,
            reason_category=request.reason_category,
            updated_at=request.updated_at,
            order=RefundOrderBrief.from_row(view.order),
            approval=_approval_of(view),
            refund_record=_record_of(view),
        )


# ------------------------------- 分页信封 -------------------------------
#
# 字段名固定 `items` / `total` / `offset` / `limit` —— 前端 `api/list.ts` 按
# `items` / `total` 认列表，改名要前后端一起改。


class MyRefundRequestPage(BaseModel):
    items: list[RefundRequestBrief]
    total: int = Field(description="我的申请总行数，与当前页无关")
    offset: int
    limit: int
