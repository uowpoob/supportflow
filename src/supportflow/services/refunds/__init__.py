"""退款业务层：资格判定、提交申请、人工审批、模拟退款。
"""

from supportflow.services.refunds.approvals import (
    decide_refund_request,
)
from supportflow.services.refunds.eligibility import (
    check_refund_eligibility,
    evaluate_eligibility,
)
from supportflow.services.refunds.errors import RefundError
from supportflow.services.refunds.queries import (
    get_refund_request_any,
    get_refund_request_for_user,
    list_all_refund_requests,
    list_refund_approvals,
    list_refund_records,
    list_refund_requests_for_user,
)
from supportflow.services.refunds.requests import create_refund_request
from supportflow.services.refunds.types import (
    ACTIVE_REQUEST_STATUSES,
    REFUND_WINDOW,
    REFUND_WINDOW_DAYS,
    Eligibility,
    RefundRequestRow,
    RefundRequestView,
)

__all__ = [
    # 异常
    "RefundError",
    # 常量与类型
    "ACTIVE_REQUEST_STATUSES",
    "REFUND_WINDOW",
    "REFUND_WINDOW_DAYS",
    "Eligibility",
    "RefundRequestRow",
    "RefundRequestView",
    # 资格
    "check_refund_eligibility",
    "evaluate_eligibility",
    # 写
    "create_refund_request",
    "decide_refund_request",
    # 读
    "get_refund_request_any",
    "get_refund_request_for_user",
    "list_all_refund_requests",
    "list_refund_approvals",
    "list_refund_records",
    "list_refund_requests_for_user",
]
