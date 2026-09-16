"""管理员接口：订单查看、退款审批、审批记录与退款执行流水。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.api.deps import require_admin
from supportflow.db.session import get_db
from supportflow.schemas import result
from supportflow.schemas.orders import OrderBrief, OrderDetail, OrderPage
from supportflow.schemas.result import Success
from supportflow.services.orders import get_order_any, list_all_orders, list_order_items

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ------------------------------ 订单 ------------------------------

@router.get("/orders", response_model=Success[OrderPage])
async def list_orders(
    offset: int = Query(0, ge=0, description="跳过的行数"),
    limit: int = Query(10, ge=1, le=100, description="每页行数，上限 100"),
    db: AsyncSession = Depends(get_db),
) -> Success[OrderPage]:
    """全部订单列表（分页）。

    管理员不做归属过滤：这个接口的语义就是"所有人的单"，准入由 router 级
    `require_admin` 保证（非管理员一律 403）。

    `limit` 设上限不是洁癖 —— 不加的话 `?limit=999999` 一次把全表拉进内存，
    等于白送一条拖垮服务的方式。
    """
    rows, total = await list_all_orders(db, offset, limit)
    page = OrderPage(
        items=[OrderBrief.from_row(order, username) for order, username in rows],
        total=total,
        offset=offset,
        limit=limit,
    )
    return Success[OrderPage](data=page)


@router.get("/orders/{order_no}", response_model=Success[OrderDetail])
async def get_order(
    order_no: str,
    db: AsyncSession = Depends(get_db),
) -> Success[OrderDetail]:
    """单个订单详情：含 `order_items` 商品明细，供审批时核对退款依据。"""
    found = await get_order_any(db, order_no)
    if found is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    order, username = found
    items = await list_order_items(db, order.id)
    return Success[OrderDetail](data=OrderDetail.from_row(order, username, items))


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
