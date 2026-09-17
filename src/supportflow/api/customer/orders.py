"""客户订单接口：我的订单列表与详情，以及退款资格判定。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.api.auth.deps import require_customer
from supportflow.db.session import get_db
from supportflow.models.entities import User
from supportflow.schemas.orders import MyOrderBrief, MyOrderDetail, MyOrderPage
from supportflow.schemas.refunds import RefundEligibilityOut
from supportflow.schemas.result import Success
from supportflow.services.orders import get_order_with_items_for_user, list_orders_for_user
from supportflow.services.refunds import check_refund_eligibility

# `/customer` 前缀与客户准入由 customer/__init__.py 统一挂，这里只声明路径与标签。
router = APIRouter(tags=["customer"])


@router.get("/orders", response_model=Success[MyOrderPage])
async def list_orders(
    offset: int = Query(0, ge=0, description="跳过的行数"),
    limit: int = Query(10, ge=1, le=100, description="每页行数，上限 100"),
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
) -> Success[MyOrderPage]:
    """我的订单列表（分页）。

    过滤条件只有一条：`orders.user_id == 当前登录用户的 id`。
    那个 id **只可能**来自 Cookie（`require_customer` 里解析出来的），
    接口上没有任何地方能传 user_id —— 不是"不信任前端"，是这条路根本不存在。

    准入已经挂在包里了，handler 里再挂一次不是重复执行（FastAPI 会缓存同一个
    依赖），只是为了拿到 `user` 对象。
    """
    rows, total = await list_orders_for_user(db, user.id, offset, limit)
    page = MyOrderPage(
        items=[MyOrderBrief.from_row(order) for order in rows],
        total=total,
        offset=offset,
        limit=limit,
    )
    return Success[MyOrderPage](data=page)


@router.get("/orders/{order_no}", response_model=Success[MyOrderDetail])
async def get_order(
    order_no: str,
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
) -> Success[MyOrderDetail]:
    """我的订单详情：含 `order_items` 商品明细（型号、数量、单价）。

    不是我的订单 / 订单不存在 → 返回**同一个**结果，不能区分。

    这不是靠"把两种情况的响应拼成一样"，而是靠**根本不分叉**：
    service 的 where 里同时带了 `order_no` 和 `user_id`，两种情况查出来
    都是 `None`，走的是同一行代码、同一个 404、同一句 detail。
    """
    found = await get_order_with_items_for_user(db, user.id, order_no)
    if found is None:
        # 文案与管理侧的 404 一模一样，不带任何"这单是谁的"的信息。
        raise HTTPException(status_code=404, detail="订单不存在")

    order, items = found
    return Success[MyOrderDetail](data=MyOrderDetail.from_row(order, items))


@router.get("/orders/{order_no}/refund-eligibility", response_model=Success[RefundEligibilityOut])
async def get_refund_eligibility(
    order_no: str,
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
) -> Success[RefundEligibilityOut]:
    """退款资格判定（只读）：能不能退、为什么、能退多少、窗口到什么时候。

    **纯查询**：不写库、不改状态、不占名额，可以随便重复调用，结果只取决于
    当前时间和订单数据。所以它是个 GET —— 一个没有副作用的判定不该用 POST。

    它和提交接口共用 `services/refunds.py::evaluate_eligibility`，
    所以不会出现"页面说能退、提交说不能退"这种自相矛盾的界面。

    不是我的订单 / 不存在，仍然是同一个 404「订单不存在」。
    """
    found = await check_refund_eligibility(db, user.id, order_no)
    if found is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    _, eligibility = found
    return Success[RefundEligibilityOut](data=RefundEligibilityOut.from_eligibility(eligibility))
