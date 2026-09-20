"""人工审批与模拟退款：行锁串行化、相同决策幂等、执行前复核。

"批准"和"退款"在同一个事务里完成，不允许出现"批准了但没退款"的中间态。

SQL 在 `repository/refund/approvals.py`（带行锁的那两条也是），事务原语在
`repository/refund/transaction.py`；这一层保留的是**决策规则**：
什么情况算重复、什么情况该报 409、执行前要不要复核。
"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.db.base import utc_now
from supportflow.models.entities import RefundRequest
from supportflow.models.enums import (
    ApprovalDecision,
    PaymentStatus,
    RefundExecutionStatus,
    RefundStatus,
)
from supportflow.repository.refund import approvals as approval_repo
from supportflow.repository.refund.transaction import _end_transaction, _reload
from supportflow.services.refunds.errors import RefundError


async def decide_refund_request(
    db: AsyncSession,
    admin_id: int,
    request_key: str,
    decision: ApprovalDecision,
    comment: str | None,
) -> RefundRequest:
    """管理员批准或拒绝；**批准即执行模拟退款**，两者在同一个事务里。

    并发与重试的处理规则（这是本函数最容易写错的地方）：

    | 情况 | 行为 |
    | --- | --- |
    | 申请还是 pending | 正常决策 |
    | 已批准过，又提交"批准" | **幂等成功**，返回当前结果，不产生第二条流水 |
    | 已拒绝过，又提交"拒绝" | 同上 |
    | 已批准，却提交"拒绝"（或反过来） | 409 冲突，禁止覆盖已有决策 |

    第 2、3 行是为了扛"HTTP 响应丢了，管理员又点了一次"；第 4 行是为了防止
    把已经生效的决策改掉。区分"相同决策重复"和"不同决策冲突"是关键 ——
    一律报冲突会让重试变成一个用户看不懂的错误，一律放行则会覆盖决策。

    整段包在一个事务里：`refund_requests` 改状态、插 `refund_approvals`、
    插 `refund_records`、改 `orders.payment_status` 要么全成，要么全不成。
    "模拟退款"只是写一行记录加改两个字段，没有外部系统，不存在
    "钱退了但状态没改"的中间窗口。
    """
    # 这一条查询带 `SELECT ... FOR UPDATE`（行锁）：把这一行锁住直到事务结束。
    # 十个并发批准会在这里排队，第一个改完状态，后面九个进来一看已经批准，
    # 走幂等分支返回 —— 这正是"并发批准只产生一条流水"的实现方式。
    request = await approval_repo.lock_request_by_key(db, request_key)
    if request is None:
        raise RefundError("request_not_found", "退款申请不存在", status_code=404)

    already_approved = request.status in (RefundStatus.APPROVED, RefundStatus.REFUNDED)
    already_rejected = request.status is RefundStatus.REJECTED
    want_approve = decision is ApprovalDecision.APPROVED

    if already_approved or already_rejected:
        same_decision = already_approved == want_approve
        if not same_decision:
            raise RefundError(
                "already_decided",
                f"该申请已被处理为「{'批准' if already_approved else '拒绝'}」，不能改成其他结果",
            )
        # 决策相同 → 幂等返回，不再插审批行、不再产生流水。
        # 但**必须结束事务再重读**：上面那句 `FOR UPDATE` 读的是最新版本，
        # 而这次没提交，调用方接下来的普通 SELECT 还会用旧快照
        # （详见 `repository/refund/transaction.py` 的长注释）。
        # 这是并发批准返回旧状态的根因。
        await _end_transaction(db)
        return await _reload(db, request)

    await approval_repo.insert_approval(
        db,
        refund_request_id=request.id,
        # admin_id 只从认证态来 —— 接口上没有这个参数，伪造不了。
        admin_id=admin_id,
        decision=decision,
        comment=comment,
    )

    if not want_approve:
        request.status = RefundStatus.REJECTED
        await _end_transaction(db)
        return await _reload(db, request)

    # 批准：先把状态推进一步，再执行模拟退款。
    # 注意 `approved` 在这条路径上是**事务内的中间态**，外部看不到它 ——
    # 保留这一步是因为接入真实支付时，执行会拆成独立事务，
    # 那时 `approved` 就是"已批准、等待执行"的持久状态。
    request.status = RefundStatus.APPROVED
    await _execute_mock_refund(db, request)

    await _end_transaction(db)
    return await _reload(db, request)


async def _execute_mock_refund(db: AsyncSession, request: RefundRequest) -> None:
    """模拟退款：写一条执行流水，把订单标成已退款，申请标成已退款。

    执行前**重新复核一遍**（验收用例 E11）：从申请提交到管理员点批准之间，
    订单金额可能被改、可能已经别处退过款。审批人点的是"批准这条申请"，
    不是"无条件给钱" —— 依据变了就该拦下来，而不是照旧执行。
    """
    order = await approval_repo.lock_order_by_id(db, request.order_id)
    if order is None:
        raise RefundError("order_not_found", "订单不存在", status_code=404)

    if order.payment_status is PaymentStatus.REFUNDED:
        raise RefundError("order_refunded", "该订单已经退款完成，不能重复退款")
    if order.payment_status is not PaymentStatus.PAID:
        raise RefundError("order_unpaid", "订单当前不是已支付状态，不能退款")
    if order.paid_amount_cents != request.amount_cents:
        # 金额对不上说明订单被改过。宁可失败也不能按旧金额退 ——
        # 多退或少退都是事故。
        raise RefundError(
            "amount_changed",
            "订单实付金额已变化，与申请金额不一致，请人工核对后再处理",
        )

    await approval_repo.insert_record(
        db,
        refund_request_id=request.id,
        refund_no=str(uuid4()),
        amount_cents=request.amount_cents,
        status=RefundExecutionStatus.SUCCEEDED,
        attempt_count=1,
        last_error=None,
        succeeded_at=utc_now(),
    )
    order.payment_status = PaymentStatus.REFUNDED
    request.status = RefundStatus.REFUNDED
