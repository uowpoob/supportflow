"""管理员订单接口：全量订单的列表与详情。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.db.session import get_db
from supportflow.schemas.orders import OrderBrief, OrderDetail, OrderPage
from supportflow.schemas.result import Success
from supportflow.services.orders import get_order_any, list_all_orders, list_order_items

# `/admin` 前缀与管理员准入由 admin/__init__.py 统一挂，这里只声明路径与标签。
router = APIRouter(tags=["admin"])


@router.get("/orders", response_model=Success[OrderPage])
async def list_orders(
    offset: int = Query(0, ge=0, description="跳过的行数"),
    limit: int = Query(10, ge=1, le=100, description="每页行数，上限 100"),
    db: AsyncSession = Depends(get_db),
) -> Success[OrderPage]:
    """全部订单列表（分页）。

    管理员不做归属过滤：这个接口的语义就是"所有人的单"，准入由 `__init__.py`
    挂的 `require_admin` 保证（非管理员一律 403）。

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
