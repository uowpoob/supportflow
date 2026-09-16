"""管理员接口：订单查看、退款审批、审批记录与退款执行流水。

审批的对象是**退款申请**（`refund_requests`），不是订单：
同一订单被拒之后还可以再申请，按订单号无法确定批的是哪一次。

`refund_approvals` 存的是**决策结果**（一个申请只批一次，该表 `refund_request_id` 唯一），
它**不是待办列表** —— 申请被批准之前，那张表里没有任何行。
"""

from fastapi import APIRouter

from supportflow.schemas import result

router = APIRouter(prefix="/admin", tags=["admin"])


# ------------------------------ 订单 ------------------------------

@router.get("/orders")
async def list_orders(offset: int = 0, limit: int = 10):
    """全部订单列表（分页）。"""
    return result.success()


@router.get("/orders/{order_no}")
async def get_order(order_no: str):
    """单个订单详情：含 `order_items` 商品明细，供审批时核对退款依据。"""
    return result.success()


# --------------------------- 退款申请 ---------------------------

@router.get("/refund-requests")
async def list_refund_requests(offset: int = 0, limit: int = 10):
    """退款申请队列（管理员的待办入口）。

    数据取自 `refund_requests`，待实现：按 `status` 过滤、按 `created_at` 排序。
    """
    return result.success()


@router.get("/refund-requests/{request_key}")
async def get_refund_request(request_key: str):
    """单条申请详情：原因原文 + 订单依据 + 已有审批记录。

    `request_key` 即 `refund_requests.request_key`（服务端生成的稳定操作 ID，唯一）。
    """
    return result.success()


@router.post("/refund-requests/{request_key}/decision")
async def decide_refund_request(request_key: str):
    """人工审批：批准或拒绝。

    待实现（同一事务内两步）：
    1. `refund_requests.status` → `approved` / `rejected`
    2. 新增一行 `refund_approvals`：`admin_id`（取登录态，不接受请求参数）、
       `decision`、`comment`

    请求体待定：`{"decision": "approved" | "rejected", "comment": "..."}`
    """
    return result.success()


# ------------------- 审批记录与退款执行流水 -------------------

@router.get("/refund-approvals")
async def list_refund_approvals(offset: int = 0, limit: int = 10):
    """审批记录查询（审计用）：只有被决策过的申请才会有行。"""
    return result.success()


@router.get("/refund-records")
async def list_refund_records(offset: int = 0, limit: int = 10):
    """退款执行流水：`attempt_count` / `last_error` / `succeeded_at`。"""
    return result.success()
