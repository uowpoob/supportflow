"""客户退款接口：提交申请与查询进度。

写流程的入口只有一个 —— `POST /refund-requests`。它是整个项目里
**唯一一处客户能触发资金状态变化**的地方，所以规则全在
`services/refunds.py`，这里只做三件事：拿身份、调业务、翻错误。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.api.auth.deps import require_customer
from supportflow.api.errors import to_http_error
from supportflow.db.session import get_db
from supportflow.models.entities import User
from supportflow.models.enums import RefundStatus
from supportflow.schemas.refunds import (
    MyRefundRequestDetail,
    MyRefundRequestPage,
    RefundRequestBrief,
    RefundRequestCreate,
)
from supportflow.schemas.result import Success
from supportflow.services.refunds import (
    RefundError,
    create_refund_request,
    get_refund_request_for_user,
    list_refund_requests_for_user,
)

router = APIRouter(tags=["customer"])


@router.post("/refund-requests", response_model=Success[MyRefundRequestDetail])
async def create_refund(
    payload: RefundRequestCreate,
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
) -> Success[MyRefundRequestDetail]:
    """提交退款申请。

    请求体里只有 `order_no` 和 `reason`（外加可选的 `conversation_id`）：
    **没有金额**（取订单实付）、**没有用户**（取登录态）、**没有状态**（新申请一律 pending）。
    少一个可传的字段，就少一条能被伪造的路径。

    重复提交是幂等的：如果这单已经有一条待审批的申请，接口会把**那一条**返回，
    不会新增第二笔。所以调用方看到 200 不代表"刚刚创建了"，
    只代表"我的申请在那儿了"。

    可能的错误：

    | 状态码 | 含义 |
    | --- | --- |
    | 404 | 订单不存在，或不是你的（两者响应完全相同） |
    | 409 | 订单本身不满足退款规则（未支付 / 未签收 / 已超期 / 已退款），`detail` 里有人话解释 |
    | 422 | 原因缺失或全空白 |
    """
    try:
        request = await create_refund_request(
            db,
            user.id,
            order_no=payload.order_no,
            reason=payload.reason,
            conversation_id=payload.conversation_id,
        )
    except RefundError as error:
        raise to_http_error(error) from error

    view = await get_refund_request_for_user(db, user.id, request.request_key)
    assert view is not None  # 刚提交的申请一定读得到
    return Success[MyRefundRequestDetail](data=MyRefundRequestDetail.from_view(view))


@router.get("/refund-requests", response_model=Success[MyRefundRequestPage])
async def list_refunds(
    offset: int = Query(0, ge=0, description="跳过的行数"),
    limit: int = Query(10, ge=1, le=100, description="每页行数，上限 100"),
    status: RefundStatus | None = Query(None, description="按状态过滤，不传就是全部"),
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
) -> Success[MyRefundRequestPage]:
    """我的退款申请列表，按提交时间倒序。

    归属过滤是查询里的一条 `Order.user_id == user.id` ——
    跟订单列表同一个套路，翻不出别人的申请。
    """
    rows, total = await list_refund_requests_for_user(db, user.id, offset, limit, status)
    page = MyRefundRequestPage(
        items=[RefundRequestBrief.from_row(row) for row in rows],
        total=total,
        offset=offset,
        limit=limit,
    )
    return Success[MyRefundRequestPage](data=page)


@router.get("/refund-requests/{request_key}", response_model=Success[MyRefundRequestDetail])
async def get_refund(
    request_key: str,
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
) -> Success[MyRefundRequestDetail]:
    """单条申请进度：当前状态 + 审批意见 + 退款执行结果。

    用 `request_key` 而不是自增 id 对外标识：自增 id 是可枚举的整数，
    换个数字就能试探别人的申请；`request_key` 是服务端生成的 UUID。

    别人的申请和不存在，同样都是这一个 404。
    """
    view = await get_refund_request_for_user(db, user.id, request_key)
    if view is None:
        raise HTTPException(status_code=404, detail="退款申请不存在")

    return Success[MyRefundRequestDetail](data=MyRefundRequestDetail.from_view(view))
