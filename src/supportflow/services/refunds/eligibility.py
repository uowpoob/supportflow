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
    """拿订单和当前时间算出能不能退。

    检查顺序是有意的，先报最具体可操作的原因：已退款 → 未支付 → 未签收 → 数据异常 → 超期 → 已有申请。
    """
    if order.payment_status is PaymentStatus.REFUNDED:
        return _deny(order, "order_refunded", "该订单已经退款完成，不能重复申请", now)

    if order.payment_status is not PaymentStatus.PAID:
        return _deny(order, "order_unpaid", "订单尚未支付，不能申请退款", now)

    # 金额只认数据库实付，不接受请求体传入；实付为 0 即无可退金额（数据层还有 amount_cents > 0 兜底）。
    if order.paid_amount_cents <= 0:
        return _deny(order, "no_payable_amount", "订单实付金额为 0，没有可退金额", now)

    # 缺签收时间即视为未签收：拿不到时间无法判断 14 天窗口，只能拒绝。
    if order.fulfillment_status is not FulfillmentStatus.DELIVERED or order.delivered_at is None:
        return _deny(order, "not_delivered", "订单尚未签收，签收后才能在 14 天内申请退款", now)

    window_ends_at = order.delivered_at + REFUND_WINDOW

    # 签收时间晚于现在 = 数据写坏；不能按超期处理，否则把数据错误掩盖成业务拒绝。
    if order.delivered_at > now:
        return _deny(order, "delivered_time_in_future", "签收时间晚于当前时间，订单数据异常，请联系人工处理", now)

    # 闭区间：delivered_at + 14 天那一瞬间仍可申请，多 1 微秒才算超期（写成 < 会误拒踩点申请）。
    if now > window_ends_at:
        return Eligibility(
            eligible=False,
            code="window_expired",
            message=f"已超过签收后 {REFUND_WINDOW_DAYS} 天的退款期限",
            amount_cents=0,
            delivered_at=order.delivered_at,
            window_ends_at=window_ends_at,
        )

    # 重复申请放最后判：它说的是"你已申请过"而非订单有问题，混在一起报会误导。
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
