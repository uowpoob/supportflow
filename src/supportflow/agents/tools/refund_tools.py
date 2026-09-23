from datetime import datetime

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession
from supportflow.services import refunds as refund_service
from supportflow.models.enums import (
    ApprovalDecision,
    RefundExecutionStatus,
    RefundStatus,
)
from supportflow.services.refunds import create_refund_request

_REFUND_CN = {
    RefundStatus.PENDING: "待审批",
    RefundStatus.APPROVED: "已批准",
    RefundStatus.REJECTED: "已拒绝",
    RefundStatus.REFUNDED: "已退款",
}

_EXECUTION_CN = {
    RefundExecutionStatus.PROCESSING: "处理中",
    RefundExecutionStatus.SUCCEEDED: "已到账",
    RefundExecutionStatus.FAILED: "打款失败",
}


def _fmt(moment: datetime | None) -> str:

    return "未记录" if moment is None else moment.strftime("%Y-%m-%d %H:%M UTC")

def _refund_line(row) -> str:
    return (
        f"- {row.order_no}｜状态 {_REFUND_CN[row.request.status]}"
        f"｜申请单号 {row.request.request_key}"
        f"｜金额 {row.request.amount_cents} 分"
        f"｜申请 {_fmt(row.request.created_at)}"

    )


def build_refund_tools(db : AsyncSession,user_id:int,conversation_id : str)->list:
    submitted_request: tuple[str, str, str, str] | None = None
    @tool
    async def list_my_refunds(status: RefundStatus | None = None) -> str:
        """当用户想看自己的退款申请时调用，比如"我的退款申请""我申请退款了没"
        "哪些还在处理中"。status 可以不传，不传就是全部；
        传的话只能是 pending（待审批）/ approved（已批准）/ rejected（已拒绝）/ refunded（已退款）。
        不需要用户 ID —— 只会返回当前登录用户自己的申请。"""
        # 跟 list_my_orders 一样给 50：模型看不到的那几条，它会当成"不存在"，
        # 而且它没有翻页的能力。
        rows, total = await refund_service.list_refund_requests_for_user(
            db, user_id, offset=0, limit=50, status=status
        )
        if not rows:
            return "你还没有提交过退款申请。"

        lines = [f"你共有 {total} 笔退款申请，按时间从新到旧：", ""]
        lines += [_refund_line(row) for row in rows]
        return "\n".join(lines)

    @tool
    async def get_refund_detail(request_key: str) -> str:
        """当用户想了解某一条退款申请办到哪一步时调用，比如"我那笔退款到哪了"
        "批了吗""钱到账没"。request_key 是申请编号，从 list_my_refunds 的结果里取，
        不是订单号（订单号是 16 位数字）。不需要用户 ID —— 只能看当前登录用户自己的申请。"""
        view = await refund_service.get_refund_request_for_user(
            db, user_id, request_key
        )
        if view is None:
            return "没有找到这条退款申请。"

        request = view.request
        lines = [
            f"- 订单 {view.order.order_no}｜金额 {request.amount_cents} 分",
            f"- 申请状态 {_REFUND_CN[request.status]}",
            f"- 申请时间 {_fmt(request.created_at)}",
            f"- 申请理由 {request.reason_original}",
        ]

        approval = view.approval
        if approval is None:
            lines.append("- 审批情况 还没有人处理")
        else:
            decision = (
                "已批准" if approval.decision == ApprovalDecision.APPROVED else "已拒绝"
            )
            lines.append(
                f"- 审批情况 {decision}｜审批人 {view.approval_admin or '未记录'}"
                f"｜{_fmt(approval.created_at)}"
            )
            if approval.comment:
                lines.append(f"- 审批备注 {approval.comment}")

        record = view.record
        if record is None:
            lines.append("- 打款情况 还未发起打款")
        else:
            lines.append(
                f"- 打款情况 {_EXECUTION_CN[record.status]}"
                f"｜已尝试 {record.attempt_count} 次"
            )
            if record.succeeded_at is not None:
                lines.append(f"- 到账时间 {_fmt(record.succeeded_at)}")
            if record.last_error:
                lines.append(f"- 最近一次失败原因 {record.last_error}")

        return "\n".join(lines)

    @tool
    async def get_refund_eligibility(order_no: str) -> str:
        """当用户问某笔订单"能不能退款""还能退吗""退款截止到几号"时调用。
        order_no 是订单号，16 位数字（例如 1260918430020001），不是用户 ID。只看资格，不会真的提交申请。"""
        found = await refund_service.check_refund_eligibility(db, user_id, order_no)
        if found is None:
            return f"没有找到订单 {order_no}。"

        _, eligibility = found
        head = "可以申请退款" if eligibility.eligible else "不能申请退款"
        lines = [f"- 订单 {order_no}：{head}｜{eligibility.message}"]
        if eligibility.eligible:
            lines.append(f"- 可退金额 {eligibility.amount_cents} 分")
        if eligibility.delivered_at is not None:
            lines.append(f"- 签收时间 {_fmt(eligibility.delivered_at)}")
        if eligibility.window_ends_at is not None:
            lines.append(f"- 退款期限截止 {_fmt(eligibility.window_ends_at)}")
        if eligibility.existing_request_key is not None:
            lines.append(f"- 已有一条退款申请 {eligibility.existing_request_key}")
        return "\n".join(lines)


    @tool(response_format="content_and_artifact")
    async def post_refund(order_no: str, reason: str) -> tuple[str, dict[str, str]]:
        """用户明确要求提交退款，且订单号和原因齐全时调用。"""
        nonlocal submitted_request
        # 同一轮模型可能并行调用多个工具；一次只办理一笔，避免留下无法等待的申请。
        if submitted_request is not None:
            submitted_order, key, status, submitted_conversation = submitted_request
            return (
                f"本轮已为订单 {submitted_order} 提交申请 {key}；订单 {order_no} 未提交，请先等待这笔申请处理完毕。",
                {"request_key": key, "status": status, "conversation_id": submitted_conversation},
            )
        request = await create_refund_request(
            db,
            user_id,
            order_no=order_no,
            reason=reason,
            conversation_id=conversation_id,
        )
        submitted_request = (order_no, request.request_key, request.status.value, request.conversation_id)
        return (
            f"申请编号：{request.request_key}，状态：{request.status.value}",
            {
                "request_key": request.request_key,
                "status": request.status.value,
                "conversation_id": request.conversation_id,
            },
        )
    
    return [list_my_refunds, get_refund_detail, get_refund_eligibility,post_refund]
