"""退款接口的请求与响应结构。

沿用 `schemas/orders.py` 立下的规矩：**界面需要什么形状就定义什么对象**，
不直接序列化 ORM。这里额外多一条 —— 客户侧和管理侧要**分成两组对象**，
因为同一张 `refund_requests` 给两边看的东西不一样：

- 客户看自己的申请：不需要 `user_id` / `username`（那本来就是他自己），
  关心的是"我的申请到哪一步了"。
- 管理员看所有人的申请：必须知道**是谁的**，还得知道"是谁批的"。

把两边硬塞进一个对象，就会出现"客户侧字段恒为空"或者"管理员侧少一半信息"
两种结局 —— 接口结构该跟使用场景走，不是跟表走。

时间字段沿用 `UtcInstant`（带 `Z`、截毫秒），理由见 `schemas/common.py` 里的长注释。

## 目录分工

| 模块 | 装什么 |
| --- | --- |
| `eligibility.py` | 资格响应（一个对象，一个出口） |
| `common.py` | 两边共用的片段：订单摘要、审批结果、退款流水 |
| `customer.py` | 客户提交、列表、详情、分页 |
| `admin.py` | 管理员决策、列表、详情、分页 |

**"输入按业务、响应按受众"** —— 请求体只有业务属性（订单号、原因），
所以 `RefundRequestCreate` 归客户侧、`RefundDecisionIn` 归管理侧；
而响应体是给人看的，客户和管理员看到的东西确实不同，就按受众分文件。
共用的那几个片段（一条审批、一笔流水在两边是同一条）放在 `common.py`，
复制两份的下场是改一处漏一处。

本文件只做 re-export，不写逻辑：路由写的是
`from supportflow.schemas.refunds import ...`，保持这个入口不变，
拆包对调用方就是零改动。
"""

from supportflow.schemas.refunds.admin import (
    AdminRefundRequestBrief,
    AdminRefundRequestDetail,
    AdminRefundRequestPage,
    RefundApprovalPage,
    RefundDecisionIn,
    RefundRecordPage,
)
from supportflow.schemas.refunds.common import (
    RefundApprovalOut,
    RefundOrderBrief,
    RefundRecordOut,
)
from supportflow.schemas.refunds.customer import (
    MyRefundRequestDetail,
    MyRefundRequestPage,
    RefundRequestBrief,
    RefundRequestCreate,
)
from supportflow.schemas.refunds.eligibility import RefundEligibilityOut

__all__ = [
    "RefundEligibilityOut",
    "RefundApprovalOut",
    "RefundOrderBrief",
    "RefundRecordOut",
    "RefundRequestCreate",
    "RefundRequestBrief",
    "MyRefundRequestDetail",
    "MyRefundRequestPage",
    "RefundDecisionIn",
    "AdminRefundRequestBrief",
    "AdminRefundRequestDetail",
    "AdminRefundRequestPage",
    "RefundApprovalPage",
    "RefundRecordPage",
]
