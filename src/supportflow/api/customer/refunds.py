"""客户退款接口：提交申请与查询进度。

三个 handler 目前都是占位实现，统一返回空信封 `{"data":{}}` —— 写流程都没接。
"""

from fastapi import APIRouter

from supportflow.schemas import result

router = APIRouter(tags=["customer"])


@router.post("/refund-requests")
async def create_refund_request():
    """提交退款申请 —— 整条写流程的入口。

    待定：请求体（`order_no` / 原因原文），以及幂等键
    （`refund_requests.request_key` 由服务端生成，重试必须复用同一条）。
    金额不接受请求参数，取订单实付金额。
    """
    return result.success()


@router.get("/refund-requests")
async def list_refund_requests(offset: int = 0, limit: int = 10):
    """我的退款申请列表。"""
    return result.success()


@router.get("/refund-requests/{request_key}")
async def get_refund_request(request_key: str):
    """单条申请进度：当前状态 + 审批意见 + 退款执行结果。

    `request_key` 即 `refund_requests.request_key`。
    """
    return result.success()
