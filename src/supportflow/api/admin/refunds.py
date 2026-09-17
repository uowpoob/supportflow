"""管理员退款接口：待办队列、人工审批、审批记录与执行流水。

前五个 handler 目前都是占位实现，统一返回空信封 `{"data":{}}`
（前端认不出这个形状，会显示成空状态）—— 写流程都没接。
"""

from fastapi import APIRouter

from supportflow.schemas import result

router = APIRouter(tags=["admin"])


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


@router.get("/refund-approvals")
async def list_refund_approvals(offset: int = 0, limit: int = 10):
    """审批记录查询（审计用）：只有被决策过的申请才会有行。"""
    return result.success()


@router.get("/refund-records")
async def list_refund_records(offset: int = 0, limit: int = 10):
    """退款执行流水：`attempt_count` / `last_error` / `succeeded_at`。"""
    return result.success()
