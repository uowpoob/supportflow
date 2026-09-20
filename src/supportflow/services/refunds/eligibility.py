"""资格规则与资格查询：这单能不能退、为什么不能退。

规则本身（`evaluate_eligibility`）是**纯函数**，不碰数据库；查询
（`check_refund_eligibility`）负责把订单和当前占名额的申请取出来喂给它。
两者分开放，是为了让规则可以被单元测试直接覆盖 —— 不用造数据库、不用起服务。

SQL 都在 `repository/refund/eligibility.py`，这一层只决定"要查什么、查出来怎么判"。
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.db.base import utc_now
from supportflow.models.entities import Order, RefundRequest
from supportflow.models.enums import FulfillmentStatus, PaymentStatus
from supportflow.repository.refund import eligibility as refund_repo
from supportflow.services.refunds.types import (
    ACTIVE_REQUEST_STATUSES,
    REFUND_WINDOW,
    REFUND_WINDOW_DAYS,
    Eligibility,
)


def evaluate_eligibility(
    order: Order,
    active_request: RefundRequest | None,
    now: datetime,
) -> Eligibility:
    """纯函数：拿订单和当前时间算出能不能退。**不碰数据库**。

    抽成纯函数的好处是规则可以被单元测试直接覆盖 —— 不需要造数据库、
    不需要起服务，"正好 14 天"和"14 天零 1 秒"这类边界一秒就能验完。

    检查顺序是有意的，先报最具体、最可操作的原因：
    已退款（不用再试了）→ 未支付（先去付款）→ 未签收（再等等）
    → 数据异常 → 超期 → 已有申请。
    """
    # 已退过款的订单永久出局 —— 它连"超期"都不该报，那是另一回事。
    if order.payment_status is PaymentStatus.REFUNDED:
        return _deny(order, "order_refunded", "该订单已经退款完成，不能重复申请", now)

    if order.payment_status is not PaymentStatus.PAID:
        return _deny(order, "order_unpaid", "订单尚未支付，不能申请退款", now)

    # 金额必须来自数据库实付，绝不允许从请求体里来。实付为 0 的订单没有可退金额，
    # 数据库那层还有 `amount_cents > 0` 兜着，这里提前把话说清楚。
    if order.paid_amount_cents <= 0:
        return _deny(order, "no_payable_amount", "订单实付金额为 0，没有可退金额", now)

    # 签收时间缺一个都算"没签收"：状态说已签收但时间为空，说明数据不完整，
    # 拿不到时间就没法判断 14 天窗口，只能拒绝。
    if order.fulfillment_status is not FulfillmentStatus.DELIVERED or order.delivered_at is None:
        return _deny(order, "not_delivered", "订单尚未签收，签收后才能在 14 天内申请退款", now)

    window_ends_at = order.delivered_at + REFUND_WINDOW

    # 签收时间在"现在"之后 —— 不可能发生，说明数据被写坏了。
    # 这种情况不能按超期处理，那样会把数据错误掩盖成业务拒绝。
    if order.delivered_at > now:
        return _deny(order, "delivered_time_in_future", "签收时间晚于当前时间，订单数据异常，请联系人工处理", now)

    # 窗口是**闭区间**：`delivered_at + 14 天` 那一瞬间仍然可以申请，
    # 多 1 微秒才算超期。写成 `<` 会把恰好踩点的申请误拒。
    if now > window_ends_at:
        return Eligibility(
            eligible=False,
            code="window_expired",
            message=f"已超过签收后 {REFUND_WINDOW_DAYS} 天的退款期限",
            amount_cents=0,
            delivered_at=order.delivered_at,
            window_ends_at=window_ends_at,
        )

    # 最后才看重复申请：前面几条都在说"这单本身行不行"，
    # 这条说的是"你已经申请过了"，混在一起报会让人以为订单有问题。
    if active_request is not None:
        return Eligibility(
            eligible=False,
            code="already_requested",
            message="该订单已有一条待审批或已批准的退款申请",
            amount_cents=0,
            delivered_at=order.delivered_at,
            window_ends_at=window_ends_at,
            existing_request_key=active_request.request_key,
        )

    return Eligibility(
        eligible=True,
        code="ok",
        message=f"可以申请整单退款，签收后 {REFUND_WINDOW_DAYS} 天内有效",
        amount_cents=order.paid_amount_cents,
        delivered_at=order.delivered_at,
        window_ends_at=window_ends_at,
    )


def _deny(order: Order, code: str, message: str, now: datetime) -> Eligibility:
    """拒绝时的公共构造。

    `delivered_at` / `window_ends_at` 照常带上（有就给）：界面即使显示"不能退"，
    也仍然需要告诉用户"你的窗口本来是到几号"，否则他只能看到一个干巴巴的"不行"。
    """
    delivered_at = order.delivered_at
    return Eligibility(
        eligible=False,
        code=code,
        message=message,
        amount_cents=0,
        delivered_at=delivered_at,
        window_ends_at=None if delivered_at is None else delivered_at + REFUND_WINDOW,
    )


async def _active_request(db: AsyncSession, order_id: int) -> RefundRequest | None:
    """该订单当前那条"占名额"的申请，没有就是 None。

    哪些状态算"占名额"是**本层的规则**（`ACTIVE_REQUEST_STATUSES`），所以由这里
    传给 repository —— 数据访问层不认识业务概念，也不该认识。

    数据库有 `active_order_id` 唯一约束保证最多一条，所以不需要 ORDER BY ——
    真要查出两行，那是约束被人删了，属于该炸的情况。

    前缀是下划线，但 `requests.py` 也要用它（幂等分支要回读那条申请）——
    同包内互相借用私有函数是可以的，它没有对外暴露成公开 API。
    """
    return await refund_repo.find_request_in_statuses(db, order_id, ACTIVE_REQUEST_STATUSES)


async def check_refund_eligibility(
    db: AsyncSession,
    user_id: int,
    order_no: str,
) -> tuple[Order, Eligibility] | None:
    """判定入口：订单不存在或不属于当前用户一律返回 `None`。

    归属条件（`Order.user_id == user_id`）和订单号写在**同一个 where** 里
    （就在 repository 那条查询里），跟订单详情一个套路 —— 两种失败天然都是 None，
    调用方无从区分，也就无从用它来探测"某个订单号是否真实存在"。
    """
    order = await refund_repo.find_order_for_user(db, user_id, order_no)
    if order is None:
        return None

    request = await _active_request(db, order.id)
    return order, evaluate_eligibility(order, request, utc_now())
