"""退款业务层：资格判定、提交申请、人工审批、模拟退款。

**所有退款规则只写在这一层。** 现在有三个调用方（客户 HTTP 路由、管理 HTTP 路由，
以后还有 Agent Tool 和暂停恢复流程），四者必须给出完全一致的答案 ——
规则复制一份出去，早晚会出现"页面说能退、提交说不能退"这种自相矛盾的界面。

两条贯穿整个包的原则：

1. **身份只从调用方传进来。** 这里的 `user_id` / `admin_id` 参数全部由认证态提供，
   函数内部没有任何地方会去读请求体里的身份字段。
2. **无权限与不存在返回同一种结果。** 归属条件全部塞进 `where`，
   查不到就是 `None`，由路由层统一翻成同一个 404 —— 见 `services/orders.py` 里那段说明。

## 目录分工（按"业务做什么"拆，不是按"谁调用"拆）

| 模块 | 装什么 |
| --- | --- |
| `errors.py` | `RefundError`（每个子模块都要用，所以单独一层） |
| `types.py` | 领域类型与不变量常量：`Eligibility` / `RefundRequestRow` / `RefundRequestView` / 窗口天数 |
| `eligibility.py` | 资格规则（纯函数）+ 资格查询 |
| `requests.py` | 提交申请、关联会话、并发防重 |
| `approvals.py` | 人工审批、执行前复核、模拟退款 |
| `queries.py` | 申请列表/详情、审批记录、退款流水，外加两个事务原语 |

**为什么不按 customer / admin 拆？** 因为"谁调用"是 `api/` 的事（那里 URL 和鉴权
确实不同），而这一层两边共用的是最不能复制的那部分：`RefundError`、资格规则、
`RefundRequestView`。拆开就只有两种结局 —— 复制两份规则，或者再开一个
`_shared.py` 让三个文件互相 import。另外 Agent Tool 既不是 customer 也不是 admin。

本文件只做 re-export，不写逻辑：路由和多处内部引用都写的是
`from supportflow.services.refunds import ...`，保持这个入口不变，
拆包对调用方就是零改动。
"""

from supportflow.services.refunds.approvals import (
    decide_refund_request,
)
from supportflow.services.refunds.eligibility import (
    check_refund_eligibility,
    evaluate_eligibility,
)
from supportflow.services.refunds.errors import RefundError
from supportflow.services.refunds.queries import (
    get_refund_request_any,
    get_refund_request_for_user,
    list_all_refund_requests,
    list_refund_approvals,
    list_refund_records,
    list_refund_requests_for_user,
)
from supportflow.services.refunds.requests import create_refund_request
from supportflow.services.refunds.types import (
    ACTIVE_REQUEST_STATUSES,
    REFUND_WINDOW,
    REFUND_WINDOW_DAYS,
    Eligibility,
    RefundRequestRow,
    RefundRequestView,
)

__all__ = [
    # 异常
    "RefundError",
    # 常量与类型
    "ACTIVE_REQUEST_STATUSES",
    "REFUND_WINDOW",
    "REFUND_WINDOW_DAYS",
    "Eligibility",
    "RefundRequestRow",
    "RefundRequestView",
    # 资格
    "check_refund_eligibility",
    "evaluate_eligibility",
    # 写
    "create_refund_request",
    "decide_refund_request",
    # 读
    "get_refund_request_any",
    "get_refund_request_for_user",
    "list_all_refund_requests",
    "list_refund_approvals",
    "list_refund_records",
    "list_refund_requests_for_user",
]
