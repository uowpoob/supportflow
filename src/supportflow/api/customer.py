"""客户接口：我的订单、退款申请、对话会话。"""

from fastapi import APIRouter,Depends

from supportflow.api.deps import require_customer
from supportflow.schemas import result

router = APIRouter(prefix="/customer", tags=["customer"], dependencies=[Depends(require_customer)])


# ------------------------------ 订单 ------------------------------

@router.get("/orders")
async def list_orders(offset: int = 0, limit: int = 10):
    """我的订单列表（分页）。"""
    return result.success()


@router.get("/orders/{order_no}")
async def get_order(order_no: str):
    """我的订单详情：含 `order_items` 商品明细（型号、数量、单价）。

    不是我的订单 / 订单不存在 → 返回**同一个**结果，不能区分。
    """
    return result.success()


@router.get("/orders/{order_no}/refund-eligibility")
async def get_refund_eligibility(order_no: str):
    """退款资格判定（只读）：能不能退、不能退的原因。

    纯查询：不写库、不改状态，可以重复调用，结果只取决于当前时间与订单数据。
    """
    return result.success()


# --------------------------- 退款申请 ---------------------------

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


# --------------------------- 对话会话 ---------------------------

@router.get("/conversations")
async def list_conversations(offset: int = 0, limit: int = 10):
    """我的对话会话列表（对应 `conversations` 表）。

    原路径 `/customer/session` 已废弃 —— "session" 在本项目里指登录会话
    （`auth_sessions`），两个 session 混在一起会看不明白。
    """
    return result.success()
