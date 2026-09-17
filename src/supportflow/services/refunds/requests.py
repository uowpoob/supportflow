"""提交退款申请：资格复核、关联会话、并发防重。

客户侧唯一的写入口。三条硬规矩都在这里落地：
金额只认订单实付、身份只从参数来、重复提交幂等（靠数据库唯一约束兜底）。
"""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.models.entities import Conversation, Order, RefundRequest
from supportflow.models.enums import RefundStatus
from supportflow.services.refunds.eligibility import _active_request, check_refund_eligibility
from supportflow.services.refunds.errors import RefundError
from supportflow.services.refunds.queries import _end_transaction, _reload


async def create_refund_request(
    db: AsyncSession,
    user_id: int,
    *,
    order_no: str,
    reason: str,
    conversation_id: str | None = None,
) -> RefundRequest:
    """提交退款申请；资格不合格一律拒绝，**金额固定取订单实付**。

    三个"不接受"：
    - 不接受请求体里的金额（`amount_cents` 根本不在入参里）
    - 不接受请求体里的 `user_id`（它只从认证态来）
    - 不接受请求体里的 `status`（新申请一律 pending）

    重复提交是幂等的：资格判定里 `already_requested` 那一条会直接把**既有的**申请
    返回去，不新建第二条。所以这个函数返回的申请不一定是"刚刚创建的"，
    调用方不需要、也无法区分 —— 对客户端来说，"我的申请已经在那儿了"就是成功。
    """
    found = await check_refund_eligibility(db, user_id, order_no)
    if found is None:
        # 与订单详情同一个 404 文案，不区分"不是你的"和"不存在"。
        raise RefundError("order_not_found", "订单不存在", status_code=404)

    order, eligibility = found

    if not eligibility.eligible:
        if eligibility.code == "already_requested":
            # 幂等分支：不新建，把既有那条原样还给调用方。
            # 同样要先结束事务再重读（见 `queries._end_transaction`）—— 这条从没写过库，
            # 用 commit 关掉事务是零副作用的，但它保证了调用方后面读到的是最新状态。
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
    db.add(request)

    try:
        await db.commit()
    except IntegrityError:
        # 走到这里只有一个原因：两个请求同时通过了上面的资格判定，
        # 后到的那个撞上了 `active_order_id` / `request_key` 唯一约束。
        # 数据库是最后一道防线，我们退回去把先到的那条读出来返回 ——
        # 用户看到的仍然是"申请已提交"，而且库里只有一条。
        await db.rollback()
        existing = await _active_request(db, order.id)
        if existing is None:
            raise
        await _end_transaction(db)
        return await _reload(db, existing)

    await db.refresh(request)
    return request


async def _resolve_conversation(
    db: AsyncSession,
    user_id: int,
    conversation_id: str | None,
    order: Order,
) -> Conversation:
    """把这次申请挂到一条会话上，`refund_requests.conversation_id` 是 NOT NULL 外键。

    为什么网页表单也要有会话？因为这条外键不是装饰：
    `conversations.id` 同时是 LangGraph checkpoint 的 `thread_id`，
    第 5 天接上 Agent 之后，"这次退款是在哪次对话里谈的"必须能对上。

    传了 `conversation_id` 就校验归属（不能把申请挂到别人的会话上）；
    没传就现建一条 —— 用户从订单页直接点"提交"时本来就不存在对话。
    """
    if conversation_id is not None:
        conversation = await db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                # 归属检查同样塞进 where，查不到就当作不存在。
                Conversation.user_id == user_id,
            )
        )
        if conversation is None:
            raise RefundError("conversation_not_found", "会话不存在", status_code=404)
        return conversation

    conversation = Conversation(user_id=user_id, title=f"退款申请 {order.order_no}")
    db.add(conversation)
    # flush 拿到自增 id 才能被 refund_requests 引用（还没提交，失败一起回滚）。
    await db.flush()
    return conversation
