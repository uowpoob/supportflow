"""退款数据访问子包：SQL 全在这里。

| 模块 | 装什么 |
| --- | --- |
| `types.py` | 查询返回的形状：`RefundRequestRow` / `RefundRequestView` |
| `queries.py` | 申请列表/详情、审批记录、退款流水 |
| `eligibility.py` | 按订单号取订单、按状态集取"占名额"的申请 |
| `requests.py` | 会话解析/新建、插入退款申请 |
| `approvals.py` | 带行锁的查询、插入审批行与退款流水 |
| `transaction.py` | 两个事务原语（结束事务、在新事务里重读） |

调用方是 `services/refunds/` —— 那是对外稳定入口，HTTP 路由和 Agent Tool 都走它。
依赖方向只有一条：services → repository；这里不许 import services 里的任何东西
（`ACTIVE_REQUEST_STATUSES` 这种业务常量由调用方传进来，见 `eligibility.py`）。
"""

from supportflow.repository.refund.approvals import (
    insert_approval,
    insert_record,
    lock_order_by_id,
    lock_request_by_key,
)
from supportflow.repository.refund.eligibility import (
    find_order_for_user,
    find_request_in_statuses,
)
from supportflow.repository.refund.queries import (
    get_refund_request_any,
    get_refund_request_for_user,
    list_all_refund_requests,
    list_refund_approvals,
    list_refund_records,
    list_refund_requests_for_user,
)
from supportflow.repository.refund.requests import (
    create_conversation,
    find_conversation_for_user,
    insert_refund_request,
)
from supportflow.repository.refund.types import RefundRequestRow, RefundRequestView

__all__ = [
    # 返回形状
    "RefundRequestRow",
    "RefundRequestView",
    # 读
    "get_refund_request_any",
    "get_refund_request_for_user",
    "list_all_refund_requests",
    "list_refund_approvals",
    "list_refund_records",
    "list_refund_requests_for_user",
    # 基础查询
    "find_order_for_user",
    "find_request_in_statuses",
    # 写
    "create_conversation",
    "find_conversation_for_user",
    "insert_approval",
    "insert_record",
    "insert_refund_request",
    # 加锁读
    "lock_order_by_id",
    "lock_request_by_key",
]
