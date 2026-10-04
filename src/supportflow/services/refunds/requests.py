"""提交退款申请：资格复核、关联会话、并发防重。

客户侧唯一的写入口。三条硬规矩都在这里落地：
金额只认订单实付、身份只从参数来、重复提交幂等（靠数据库唯一约束兜底）。

SQL 在 `repository/refund/requests.py`，事务原语在 `repository/refund/transaction.py`；
这一层保留的是**规则**：什么时候复用既有申请、什么时候该报错、撞了唯一约束之后怎么办。
"""

from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.models.entities import Conversation, Order, RefundRequest
from supportflow.models.enums import RefundStatus
from supportflow.repository.refund import requests as request_repo
from supportflow.repository.refund.transaction import (
    _end_transaction,
    _reload,
    _rollback,
)
from supportflow.services.refunds.eligibility import _active_request, check_refund_eligibility
from supportflow.services.refunds.errors import RefundError


async def create_refund_request(
    db: AsyncSession,
    user_id: int,
    *,
    order_no: str,
    reason: str,
    conversation_id: str | None = None,
) -> RefundRequest:
    """提交退款申请；资格不合格一律拒绝，**金额固定取订单实付**。

    """
    found = await check_refund_eligibility(db, user_id, order_no)
    if found is None:
        # 与订单详情同一个 404 文案，不区分"不是你的"和"不存在"。
        raise RefundError("order_not_found", "订单不存在", status_code=404)

    order, eligibility = found

    if not eligibility.eligible:
        if eligibility.code == "already_requested":
            # 幂等分支：不新建，把既有那条原样返回；先结束事务再重读（见 repository/refund/transaction.py）。
            existing = await _active_request(db, order.id)
            assert existing is not None  # 判定刚查过，并发删除的可能性交给下面的兜底
            await _end_transaction(db)
            return await _reload(db, existing)
        raise RefundError(eligibility.code, eligibility.message)

    conversation = await _resolve_conversation(db, user_id, conversation_id, order)

    request = RefundRequest(
        # 服务端生成稳定操作 ID：客户端不参与生成，也就无法用它去猜别人的申请。
        request_key=str(uuid4()),
        order_id=order.id,
        conversation_id=conversation.id,
        # 金额只认库里的实付，以整数分保存，不接受外部指定。
        amount_cents=order.paid_amount_cents,
        reason_original=reason.strip(),
        # 分类留给第 5 天的模型来做，现在不猜。
        reason_category=None,
        status=RefundStatus.PENDING,
    )
    await request_repo.insert_refund_request(db, request)

    try:
        await _end_transaction(db)
    except IntegrityError:
        # 后到的请求撞上唯一约束时，回退读先到那条返回：用户仍看到"申请已提交"、库里只有一条。
        await _rollback(db)
        existing = await _active_request(db, order.id)
        if existing is None:
            raise
        await _end_transaction(db)
        return await _reload(db, existing)

    return await _reload(db, request)


async def _resolve_conversation(
    db: AsyncSession,
    user_id: int,
    conversation_id: str | None,
    order: Order,
) -> Conversation:
    """把这次申请挂到一条会话上，`refund_requests.conversation_id` 是 NOT NULL 外键。

    """
    if conversation_id is not None:
        conversation = await request_repo.find_conversation_for_user(
            db, user_id, conversation_id
        )
        if conversation is None:
            raise RefundError("conversation_not_found", "会话不存在", status_code=404)
        return conversation

    # flush 拿到自增 id 才能被 refund_requests 引用（还没提交，失败一起回滚）。
    return await request_repo.create_conversation(
        db, user_id, f"退款申请 {order.order_no}"
    )
