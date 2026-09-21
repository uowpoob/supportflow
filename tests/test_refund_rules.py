"""退款规则 `evaluate_eligibility` 的纯函数单测：不碰数据库、不起服务。

单独一个文件的理由：`evaluate_eligibility` 是整条退款链的判据 ——
它算错，界面就会显示"能退"然后提交被拒（或者反过来，让人白跑一趟）。
纯函数意味着规则可以在这几毫秒里被逐条钉死，不需要造订单、不需要起服务。

时钟固定成 2026-09-14，与 `docs/acceptance-cases.md` 约定的固定时钟一致。
时间是**无时区 UTC**，和 `db.base.utc_now()` 写进 MySQL 的形态相同。
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
import unittest

from supportflow.models import Order, RefundRequest
from supportflow.models.enums import FulfillmentStatus, PaymentStatus, RefundStatus
from supportflow.services.refunds.eligibility import evaluate_eligibility
from supportflow.services.refunds.types import REFUND_WINDOW, REFUND_WINDOW_DAYS

NOW = datetime(2026, 9, 14, 0, 0, 0)


def make_order(**changes) -> Order:
    """一个"什么条件都满足"的订单 —— 用例只改它关心的那一项。

    默认值全部取"可以退"的那一侧：这样每个用例里唯一的变量就是它显式改的字段，
    一旦失败，原因不需要再猜。没有数据库，对象只是内存里的值对象。
    """
    defaults = dict(
        order_no="1260918430020001",
        user_id=1,
        paid_amount_cents=29900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        delivered_at=NOW - timedelta(days=1),
    )
    return Order(**{**defaults, **changes})


def make_active_request(key: str = "4099285177330001") -> RefundRequest:
    """一条"占着名额"的申请（待审批）。纯函数只读它的 `request_key`。"""
    return RefundRequest(
        request_key=key, order_id=1, conversation_id="demo-chat",
        amount_cents=29900, reason_original="耳机无声", status=RefundStatus.PENDING,
    )


class EligibilityRuleTests(unittest.TestCase):
    def test_eligible_order_reports_amount_and_window_from_the_order(self):
        order = make_order()
        result = evaluate_eligibility(order, None, NOW)

        self.assertTrue(result.eligible)
        self.assertEqual(result.code, "ok")
        self.assertIsNone(result.existing_request_key)
        # 金额**直接取库里的实付**，不接受任何外部传入值 —— 这是防篡改的根。
        self.assertEqual(result.amount_cents, order.paid_amount_cents)
        self.assertEqual(result.delivered_at, order.delivered_at)
        self.assertEqual(result.window_ends_at, order.delivered_at + REFUND_WINDOW)
        self.assertIn(str(REFUND_WINDOW_DAYS), result.message)

    def test_window_is_closed_on_both_sides_of_the_boundary(self):
        """`签收 + 14 天` 那一瞬间仍可申请，多 1 微秒才算超期（闭区间）。"""
        order = make_order(delivered_at=NOW - REFUND_WINDOW)

        self.assertEqual(evaluate_eligibility(order, None, NOW).code, "ok")
        self.assertEqual(
            evaluate_eligibility(order, None, NOW + timedelta(microseconds=1)).code,
            "window_expired",
        )

        # 反向再验一次：窗口结束前 1 微秒也必须拒绝，不能把边界写成开区间。
        overdue = make_order(delivered_at=NOW - REFUND_WINDOW - timedelta(microseconds=1))
        self.assertEqual(evaluate_eligibility(overdue, None, NOW).code, "window_expired")

    def test_every_rejection_branch_has_its_own_code(self):
        cases = [
            ("已退款", "order_refunded", dict(payment_status=PaymentStatus.REFUNDED)),
            ("未支付", "order_unpaid", dict(payment_status=PaymentStatus.UNPAID)),
            ("实付为 0", "no_payable_amount", dict(paid_amount_cents=0)),
            ("未发货", "not_delivered", dict(fulfillment_status=FulfillmentStatus.UNSHIPPED)),
            ("已发货未签收", "not_delivered", dict(fulfillment_status=FulfillmentStatus.SHIPPED)),
            # 状态说签收了但时间为空：数据不完整，拿不到时间就没法算窗口，只能拒绝。
            ("签收时间为空", "not_delivered", dict(delivered_at=None)),
            (
                "签收在未来",
                "delivered_time_in_future",
                dict(delivered_at=NOW + timedelta(seconds=1)),
            ),
            (
                "超过 14 天",
                "window_expired",
                dict(delivered_at=NOW - REFUND_WINDOW - timedelta(microseconds=1)),
            ),
        ]

        for label, code, changes in cases:
            with self.subTest(case=label):
                order = make_order(**changes)
                result = evaluate_eligibility(order, None, NOW)

                self.assertFalse(result.eligible)
                self.assertEqual(result.code, code)
                # 拒绝时金额恒为 0：不能给界面留一个"不能退但写着 299 元"的歧义。
                self.assertEqual(result.amount_cents, 0)
                self.assertTrue(result.message)
                self.assertIsNone(result.existing_request_key)
                # 界面即使显示"不能退"，也要能告诉用户窗口本来到几号。
                self.assertEqual(result.delivered_at, order.delivered_at)
                expected_window = (
                    None if order.delivered_at is None else order.delivered_at + REFUND_WINDOW
                )
                self.assertEqual(result.window_ends_at, expected_window)

    def test_more_specific_reason_wins_when_several_conditions_fail(self):
        """多个条件同时不满足时，报出的必须是**最具体、最可操作**的那条。

        顺序错的表现很隐蔽：用户照着提示改完，发现还是退不了，然后投诉"提示是错的"。
        """
        # 已退过款的订单连"超期"都不该报 —— 超期会让人以为等一等或者申诉还有戏。
        both = make_order(
            payment_status=PaymentStatus.REFUNDED,
            delivered_at=NOW - REFUND_WINDOW - timedelta(days=30),
        )
        self.assertEqual(evaluate_eligibility(both, None, NOW).code, "order_refunded")

        # 未支付 + 未签收 → 先让他去付款，签收是付款之后的事。
        unpaid = make_order(payment_status=PaymentStatus.UNPAID, delivered_at=None)
        self.assertEqual(evaluate_eligibility(unpaid, None, NOW).code, "order_unpaid")

        # 超期 + 已有申请 → 报超期：这单本身就不行了，说"你申请过了"会指向错误的下一步。
        expired = make_order(
            delivered_at=NOW - REFUND_WINDOW - timedelta(microseconds=1)
        )
        self.assertEqual(
            evaluate_eligibility(expired, make_active_request(), NOW).code, "window_expired"
        )

        # 状态说"未签收"时，就算时间字段是未来也只报 not_delivered ——
        # "还没签收"比"时间异常"更具体，也更是用户能理解的那件事。
        early = make_order(
            fulfillment_status=FulfillmentStatus.SHIPPED, delivered_at=NOW + timedelta(days=1)
        )
        self.assertEqual(evaluate_eligibility(early, None, NOW).code, "not_delivered")

        # 状态说"已签收"、时间却在未来 —— 这才是数据异常，不能糊成"还没签收"。
        broken = make_order(delivered_at=NOW + timedelta(days=1))
        self.assertEqual(
            evaluate_eligibility(broken, None, NOW).code, "delivered_time_in_future"
        )

    def test_active_request_is_reported_with_its_key(self):
        """已有进行中的申请：判定为不可退，并把申请号带出来给界面做跳转。"""
        request = make_active_request()
        order = make_order()
        result = evaluate_eligibility(order, request, NOW)

        self.assertFalse(result.eligible)
        self.assertEqual(result.code, "already_requested")
        self.assertEqual(result.existing_request_key, request.request_key)
        self.assertEqual(result.amount_cents, 0)
        # 窗口信息照常给：这条申请被拒之后，用户还要知道剩余时间够不够再提一次。
        self.assertEqual(result.window_ends_at, order.delivered_at + REFUND_WINDOW)

    def test_amount_follows_the_order_not_any_other_source(self):
        """可退金额永远等于订单实付 —— 换几个数值验证它确实在跟着订单走。"""
        for amount in (1, 999, 123456789):
            with self.subTest(amount_cents=amount):
                order = make_order(paid_amount_cents=amount)
                self.assertEqual(evaluate_eligibility(order, None, NOW).amount_cents, amount)

    def test_result_is_immutable(self):
        """判定结果是值对象：拿到之后谁都别想改它，否则同一个结果会被下游改出第二种含义。"""
        result = evaluate_eligibility(make_order(), None, NOW)
        with self.assertRaises(FrozenInstanceError):
            result.eligible = False


if __name__ == "__main__":
    unittest.main()
