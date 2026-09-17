"""管理员退款接口：待办队列、人工审批、审批记录与执行流水。

三张表的分工容易混，先记清楚再用：

| 表 | 是什么 | 什么时候有行 |
| --- | --- | --- |
| `refund_requests` | 客户提交的**申请**（待办就查它，`status='pending'`） | 客户一提交就有 |
| `refund_approvals` | 管理员做出的**决策**（审计凭据） | 只有被批准/拒绝过才有 |
| `refund_records` | 模拟退款的**执行流水** | 只有真正退过钱才有 |

所以"待办列表"绝不能用 `refund_approvals` —— 批准之前那张表里根本没有对应行，
拿它当待办会永远查出空数组。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.api.auth.deps import require_admin
from supportflow.api.errors import to_http_error
from supportflow.db.session import get_db
from supportflow.models.entities import User
from supportflow.models.enums import RefundStatus
from supportflow.schemas.refunds import (
    AdminRefundRequestBrief,
    AdminRefundRequestDetail,
    AdminRefundRequestPage,
    RefundApprovalOut,
    RefundApprovalPage,
    RefundDecisionIn,
    RefundRecordOut,
    RefundRecordPage,
)
from supportflow.schemas.result import Success
from supportflow.services.refunds import (
    RefundError,
    decide_refund_request,
    get_refund_request_any,
    list_all_refund_requests,
    list_refund_approvals,
    list_refund_records,
)

router = APIRouter(tags=["admin"])


@router.get("/refund-requests", response_model=Success[AdminRefundRequestPage])
async def list_refund_requests(
    offset: int = Query(0, ge=0, description="跳过的行数"),
    limit: int = Query(10, ge=1, le=100, description="每页行数，上限 100"),
    status: RefundStatus | None = Query(
        None, description="按状态过滤；待办页面传 pending，不传就是全部"
    ),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Success[AdminRefundRequestPage]:
    """退款申请队列（管理员的待办入口）。

    管理员看的是**所有人的**申请，所以这里不做归属过滤 ——
    权限已经在 `admin/__init__.py` 那层由 `require_admin` 拦掉了，
    这里再过滤一道没意义（他要看的就是全部）。

    `status` 做成可选参数而不是写死 `pending`：审批记录页要看已决的申请时，
    不用再开一个接口。
    """
    rows, total = await list_all_refund_requests(db, offset, limit, status)
    page = AdminRefundRequestPage(
        items=[AdminRefundRequestBrief.from_row(row) for row in rows],
        total=total,
        offset=offset,
        limit=limit,
    )
    return Success[AdminRefundRequestPage](data=page)


@router.get("/refund-requests/{request_key}", response_model=Success[AdminRefundRequestDetail])
async def get_refund_request(
    request_key: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Success[AdminRefundRequestDetail]:
    """单条申请详情：原因原文 + 订单依据 + 已有审批 + 退款流水。

    审批人做判断要的四样东西一次给全 —— 让他再去点开订单页翻实付金额和签收时间，
    等于鼓励"不看依据就点批准"。
    """
    view = await get_refund_request_any(db, request_key)
    if view is None:
        raise HTTPException(status_code=404, detail="退款申请不存在")

    return Success[AdminRefundRequestDetail](data=AdminRefundRequestDetail.from_view(view))


@router.post("/refund-requests/{request_key}/decision", response_model=Success[AdminRefundRequestDetail])
async def decide_refund_request_endpoint(
    request_key: str,
    payload: RefundDecisionIn,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Success[AdminRefundRequestDetail]:
    """人工审批：批准或拒绝。**批准即执行模拟退款。**

    同一事务里做完四件事：改 `refund_requests.status`、插 `refund_approvals`、
    插 `refund_records`、把 `orders.payment_status` 改成 `refunded`。
    要么全成，要么全不成 —— 不存在"钱退了但状态没改"的中间状态。

    幂等规则（重试友好，但不允许覆盖决策）：

    - 重复提交**相同**决策 → 返回当前结果，不会产生第二条流水
    - 用**不同**决策去打已决的申请 → 409，禁止覆盖

    `admin_id` 只能来自登录态（`require_admin` 解析出来的用户），
    请求体里没有这个字段 —— 跟客户侧不接受 `user_id` 是同一条边界。
    """
    try:
        await decide_refund_request(
            db,
            admin.id,
            request_key,
            decision=payload.decision,
            comment=payload.comment,
        )
    except RefundError as error:
        raise to_http_error(error) from error

    # 返回决策后的完整详情，前端直接拿它替换本地状态，不用再发一次 GET。
    view = await get_refund_request_any(db, request_key)
    assert view is not None
    return Success[AdminRefundRequestDetail](data=AdminRefundRequestDetail.from_view(view))


@router.get("/refund-approvals", response_model=Success[RefundApprovalPage])
async def list_refund_approvals_endpoint(
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Success[RefundApprovalPage]:
    """审批记录查询（审计用）：只有被决策过的申请才会有行。

    这里查的是 `refund_approvals`，不是待办 —— 待办走 `/refund-requests?status=pending`。
    """
    rows, total = await list_refund_approvals(db, offset, limit)
    page = RefundApprovalPage(
        items=[
            RefundApprovalOut.from_row(row[0], row[3], request_key=row[1], order_no=row[2])
            for row in rows
        ],
        total=total,
        offset=offset,
        limit=limit,
    )
    return Success[RefundApprovalPage](data=page)


@router.get("/refund-records", response_model=Success[RefundRecordPage])
async def list_refund_records_endpoint(
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Success[RefundRecordPage]:
    """退款执行流水：`attempt_count` / `last_error` / `succeeded_at`。

    流水是"钱真的动了"的唯一凭据，所以它和申请是两张表 ——
    有申请不代表退过款（可能还在 pending 或被拒），有流水才代表执行过。
    """
    rows, total = await list_refund_records(db, offset, limit)
    page = RefundRecordPage(
        items=[
            RefundRecordOut.from_row(row[0], request_key=row[1], order_no=row[2])
            for row in rows
        ],
        total=total,
        offset=offset,
        limit=limit,
    )
    return Success[RefundRecordPage](data=page)
