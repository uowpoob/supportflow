"""退款查询的返回形状：列表行、详情视图。

这两个 dataclass 属于数据访问层 —— 它们描述的是"查询返回什么"，
跟 `services/refunds/types.py` 里的 `Eligibility`（业务判定结果）不是一类东西：
`Eligibility` 是规则算出来的结论，这里两个只是把几行 ORM 拼在一起。

放在这一层是为了保持依赖单向：`schemas/` 和 `services/` 都可以引用它们，
而 `repository/` 不必反过来去 import 业务层的类型。

`services/refunds/types.py` 把这两个名字重新导出了一遍，所以
`from supportflow.services.refunds.types import RefundRequestRow` 这种老写法照旧能用。
"""

from dataclasses import dataclass

from supportflow.models.entities import Order, RefundApproval, RefundRecord, RefundRequest


@dataclass(frozen=True,slots=True)
class RefundRequestRow:
    """列表行：申请本身 + 订单号 [+ 归属信息（仅管理侧）]。

    `user_id` / `username` 是可选的：客户侧列表查的是"我的申请"，
    归属恒等于他自己，带上纯属噪音（也就没必要 join users）。
    """

    request: RefundRequest
    order_no: str
    user_id: int | None = None
    username: str | None = None


@dataclass(frozen=True,slots=True)
class RefundRequestView:
    """详情：申请 + 订单依据 + 已有审批 + 退款流水。

    四个对象一起给出去，是因为"这条申请该不该批"这个判断需要它们同时在手边：
    订单给出实付与签收时间，审批行说明是否已决策，流水说明是否真的退过钱。
    `approval_admin` 单独留一个字段（而不是塞进 approval）是因为它是 `users`
    表里的名字，管理侧要显示"谁批的" —— 审计信息不能只留一个 admin_id。
    """

    request: RefundRequest
    order: Order
    username: str | None
    approval: RefundApproval | None
    approval_admin: str | None
    record: RefundRecord | None
