"""退款资格判定的响应。

只有一个对象，因为资格判定只有一个出口：能不能退、为什么、能退多少、窗口到什么时候。
"""

from pydantic import BaseModel, Field

from supportflow.schemas.common import UtcInstantOrNull
from supportflow.services.refunds.types import Eligibility


class RefundEligibilityOut(BaseModel):
    """能不能退、为什么、能退多少、窗口到什么时候。

    `reason_code` 和 `reason_text` 两个都给：前端按 `code` 决定按钮状态，
    用户按 `text` 理解原因。只给一个的话，要么前端靠中文字符串做判断（改文案就崩），
    要么用户看到一个代码。
    """

    eligible: bool
    reason_code: str
    reason_text: str
    amount_cents: int
    delivered_at: UtcInstantOrNull
    window_ends_at: UtcInstantOrNull
    existing_request_key: str | None = Field(
        default=None, description="已有进行中的申请时给出它的编号，前端可直接跳过去"
    )

    @classmethod
    def from_eligibility(cls, eligibility: Eligibility) -> "RefundEligibilityOut":
        return cls(
            eligible=eligibility.eligible,
            reason_code=eligibility.code,
            reason_text=eligibility.message,
            amount_cents=eligibility.amount_cents,
            delivered_at=eligibility.delivered_at,
            window_ends_at=eligibility.window_ends_at,
            existing_request_key=eligibility.existing_request_key,
        )
