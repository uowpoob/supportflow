from fastapi import APIRouter

from supportflow.schemas import result

router = APIRouter(prefix="/admin",tags=["admin"])

#管理员界面 左侧显示订单 退款申请等任务
@router.get("/")
async def root():
    return result.success()

#查看订单表
@router.get("/orders")
async def list_orders(offset: int = 0, limit: int = 10):
    return result.success()

#查看退款列表
@router.get("/refund_approvals")
async def list_refund_approvals(offset: int = 0, limit: int = 10):
    return result.success()

#操作退款 人工审批
@router.post("/deal_refund_approvals/{order_id}")
async def deal_refund_approvals(order_id: int):
    return result.success()


