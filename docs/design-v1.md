> 表结构以 [当前七表设计](database-schema.md) 和 ORM 实体为准；本文中的旧版六表草案仅供历史参考。

# SupportFlow v1 设计：业务流程、数据模型、文件规划

本文件是第一版实现的落地设计。
它不替代 `project-scope.md`（业务范围）与 `acceptance-cases.md`（验收用例），
只回答一个更窄的问题：**这些东西具体长成哪些文件、哪些表、哪些字段。**

---

## 0. 设计主轴

系统有两条跑道，只在两个点交汇。

| | 模型跑道 | 代码跑道 |
| --- | --- | --- |
| 负责 | 意图、槽位、选工具、组织回答 | 鉴权、金额、资格、状态迁移、幂等 |
| 特性 | 可错，需要评测与引用 | 必须确定，必须可单测 |
| 失败表现 | 幻觉、指代错误、漏问 | 越权、重复退款、状态覆盖 |

两个交汇点：

1. **读**：`tool` 携带身份调 `services`，取真实数据。
2. **写**：`tool` 携带业务参数调 `services`；**金额与 user_id 不在入参里**。

第 2 条是硬约束，不是约定。实现方式是**签名里没有这两个参数**——
模型不是"被要求不能指定金额"，而是**没有任何位置可以填**。
这比在提示词里写"不要指定金额"可靠得多。

---

## 1. 业务流程模拟

### 1.1 只读流程：订单查询

```
客户: "A1001 到哪了"
  -> POST /conversations/{conv_no}/messages      （④ 步才有，本步先做 GET /orders/{no}）
  认证 -> Actor(user_id=1, role=customer, user_no="U1")
  会话归属校验: conversations.user_id == 1 ? 否则 404
  -> [意图] order_query
  -> [tool] query_order(order_no="A1001")
       -> services.orders.get_order_for_user(session, actor=..., order_no="A1001")
            SELECT ... WHERE order_no = 'A1001' AND user_id = :actor.user_id
            命中 -> Order
            未命中 -> OrderNotFound
  -> [回答] 组织自然语言，附订单真实字段
```

关键点：**"不属于我"与"不存在"返回同一个 `OrderNotFound`**，
在 `services` 层就抹平，不依赖提示词约束模型别说漏。

### 1.2 写流程：退款申请 -> 审批 -> 执行

分三段，中间被人工审批切断。

**第一段：申请（模型驱动，写 MySQL）**

```
客户: "A1001 左耳无声，给我退款"
  -> [意图] refund_request，槽位 order_no=A1001, reason=左耳无声
  -> 槽位不全（缺 order_no 或 reason）-> 追问，不进写路径
  -> [tool] check_refund_eligibility(order_no="A1001")       只读，不改状态
       -> EligibilityResult(eligible=True, amount_cents=29900, ...)
  -> [回答] "A1001 可全额退款 299.00 元，确认提交申请？"
客户: "确认"
  -> [tool] submit_refund_request(order_no="A1001", reason="左耳无声")
       -> 内部重新做一次资格检查（不信上一次结论）
       -> 事务: INSERT refund_requests(status='pending', amount_cents=29900, ...)
                若撞唯一约束 -> 返回既有活跃申请，不新增、不报错
       -> COMMIT
  -> 图状态写入 PostgreSQL checkpoint
  -> interrupt() 挂起，等待审批
```

**第二段：审批（不经过模型）**

```
管理员 M1: POST /admin/refund-requests/{request_no}/decision  {"decision":"approve"}
  认证 -> role == admin ? 否则 403 且不写任何记录
  -> 同一 MySQL 事务内:
       UPDATE refund_requests SET status='approved', decided_by=?, decided_at=?
         WHERE request_no=? AND status='pending'
         affected_rows == 0 -> RefundAlreadyDecided 异常（并发下只有一个赢）
       INSERT refund_transactions(refund_request_id=?, idempotency_key=?, ...)
         撞唯一约束 -> 说明已退过，读取既有流水返回
       UPDATE orders SET status='refunded' WHERE id=? AND status='paid'
         affected_rows == 0 -> 抛异常回滚，记录原因（订单状态已被改动）
     COMMIT
  -> 事务之外：恢复图 / 通知，失败不影响 MySQL 结果
```

审批与退款**在同一个 MySQL 事务**：要么都成，要么都不成。
`E01`（MySQL 为 pending、流水 0 条）就是这个边界的断言。

**第三段：恢复**

```
重启后:
  从 MySQL 读所有 pending / approved 的申请
  逐个按 conversations.conv_no 找 PostgreSQL checkpoint
    有 -> 恢复图，位置仍是"等待审批"
    无 -> 不新建上下文，标记"可凭 MySQL 状态重建"
  恢复入口先核一次 MySQL 状态
    若 MySQL 已 refunded 而 checkpoint 还停在待审批 -> 以 MySQL 为准，不执行
```

这条是 `E07 / E10 / E12` 的答案：**MySQL 是权威，checkpoint 是缓存**。

### 1.3 状态机

```
                   approve
        ┌──────────────────────> approved ──execute──> refunded
        │                            ^                    (终态)
pending ┤                            │ 执行失败回退，保留可重试
        │                            └────────────────────
        └── reject ──> rejected (终态)
```

只有 `pending -> approved -> refunded` 与 `pending -> rejected` 两条迁移路径。
**不引入 `executing` 中间态**：退款与状态迁移在同一个事务里，
事务要么提交要么回滚，不会留下中间态。等未来接真实支付网关
（跨进程、可能悬挂）时再补这个状态。

迁移一律用 `UPDATE ... WHERE status = <期望的旧值>` 加 `affected_rows` 守卫，
不做"先 SELECT 判断再 UPDATE"——后者在并发下会双写。

### 1.4 资格判定的分支顺序

顺序本身就是设计，不能打乱：

```python
delta = now - order.delivered_at

1. order.user_id != actor.user_id      -> ORDER_NOT_FOUND      # 先鉴权，不泄露存在性
2. order.paid_at is None               -> NOT_PAID
3. order.delivered_at is None          -> NOT_DELIVERED
4. order.status == "refunded"          -> ALREADY_REFUNDED
5. delta < 0                           -> DELIVERY_IN_FUTURE   # 数据异常，单独错误码
6. delta > 14 * 24h                    -> WINDOW_EXPIRED
7. 存在活跃申请                         -> ACTIVE_REQUEST_EXISTS
8. 否则                                 -> eligible，金额取 order.amount_cents
```

- 第 1 步必须最先：否则"未支付"和"超期"的报错会变成订单是否存在的旁路信道（`D01`）。
- 第 5 步单独成码：`B09`（签收时间在未来）要求"报告数据异常"而不是普通拒绝。
- 第 6 步用 `14 * 24h` 的秒级比较，不是"天数差"：
  `B07` 恰好 14 天要**通过**，`B08` 14 天加 1 秒要**拒绝**，只有连续时间轴能满足。
- 判定用**返回值**而不是异常：不合格是预期内的正常结果，要把原因交给模型去解释。
  而越权、不存在用**异常**，因为它不该进入模型的可见上下文。

规则：**可预期的业务分支返回结果，不可预期的违规抛异常。**

---

## 2. 数据模型

### 2.1 全局约定

| 项 | 约定 | 理由 |
| --- | --- | --- |
| 金额 | `BIGINT` 整数分，列名统一 `*_cents` | 浮点会丢精度；`amount_cents=29900` 就是 299.00 元 |
| 时间 | 一律 UTC，列类型 `DATETIME(6)` | `TIMESTAMP` 会按会话时区转换，且 2038 溢出；`DATETIME` 不转换，UTC 由应用层保证 |
| 主键 | 内部 `BIGINT AUTO_INCREMENT` | 不用业务号做外键，避免字符串外键与改号 |
| 对外标识 | 单独 `*_no` 列 + 唯一索引 | `A1001` 可读、可写文档、可出现在用例里；`id` 不外露 |
| 状态列 | `VARCHAR(16)` + Python 枚举 + `CHECK` | 不用 MySQL `ENUM`：改值要 `ALTER TABLE`，且 ORM 映射别扭 |
| 时间戳 | `created_at` / `updated_at` 由 Mixin 统一 | 避免每张表各写一遍 |
| 一致性 | 只做简单 `CHECK`（枚举、金额 > 0） | MySQL 的 `CHECK` 8.0.16+ 才真正生效，复杂断言会让种子数据难写，交给 service 与测试 |

### 2.2 表设计

六张表。前四张是"事实"，后两张是"流程记录"。

---

**`users`**

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | BIGINT PK | 内部主键，做外键用 |
| `user_no` | VARCHAR(32) UNIQUE | 对外标识：`U1` / `U2` / `M1` |
| `role` | VARCHAR(16) | `customer` / `admin` |
| `created_at` | DATETIME(6) | |

`role` 是审批接口的唯一鉴权依据（`D06`）。

---

**`orders`**

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | BIGINT PK | |
| `order_no` | VARCHAR(32) UNIQUE | `A1001` |
| `user_id` | BIGINT FK -> users.id | 归属，索引 |
| `product_name` | VARCHAR(128) | 商品名 |
| `product_sku` | VARCHAR(64) NULL | 型号，`C02` 的精确匹配要用 |
| `amount_cents` | BIGINT | **实付金额**，唯一权威来源 |
| `status` | VARCHAR(16) | `created` / `paid` / `delivered` / `refunded` |
| `paid_at` | DATETIME(6) NULL | 未支付为 NULL |
| `delivered_at` | DATETIME(6) NULL | 未签收为 NULL |
| `created_at` / `updated_at` | DATETIME(6) | |

索引：`(user_id, status)`。

两处刻意的设计：

- **`status` 与 `paid_at`/`delivered_at` 同时存在，不互相推导。**
  `status` 是业务态（给人看、给状态机用），时间列是规则输入（给资格判定用）。
  `B06`（已支付未签收）= `status='paid' AND delivered_at IS NULL`，两个都需要。
- **商品名直接放订单表，是简化。** 真实订单是多商品，应拆 `order_items`。
  第一版保留简化，因为检索层的商品过滤走 Milvus 元数据，不必真进关系表。
  **代价**：被问到"一单多商品怎么办"时要能说清这是有意取舍。

---

**`conversations`**

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | BIGINT PK | |
| `conv_no` | VARCHAR(40) UNIQUE | 对外会话 ID，**同时是 PostgreSQL checkpoint 的 `thread_id`** |
| `user_id` | BIGINT FK -> users.id | 归属，权限校验的唯一依据 |
| `title` | VARCHAR(128) NULL | 会话列表展示 |
| `status` | VARCHAR(16) | `active` / `closed` |
| `created_at` / `updated_at` | DATETIME(6) | |

索引：`(user_id, updated_at DESC)`。

`conv_no` 复用为 `thread_id` 是刻意的：这样 `D03`（U2 猜 U1 的会话 ID）
就是**一次 MySQL 归属查询**，在碰 PostgreSQL 之前就拒掉，
符合"先校验归属再读取 checkpoint"的要求。

---

**`conversation_slots`**

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | BIGINT PK | |
| `conversation_id` | BIGINT FK -> conversations.id | |
| `slot_key` | VARCHAR(32) | `current_order_no` / `last_refund_request_no` |
| `slot_value` | VARCHAR(128) | |
| `updated_at` | DATETIME(6) | |

约束：`UNIQUE(conversation_id, slot_key)`。

**这是我加的表，需要你拍板。** 它解决 `A05 / A06 / A07 / D04`：
"查 A1001 后说'这个坏了'"要能取回订单号，"新会话不翻旧账"要求槽位挂在会话上。

放 MySQL 而不是 LangGraph state 的理由：

1. **顺序干净**：归属校验在 MySQL，通过之后才可能读槽位。若槽位在 state 里，
   就得先读 checkpoint 才能拿槽位，与"先校验归属"的顺序纠缠。
2. **可降级**：PostgreSQL 挂掉（`E12`）时槽位还在，agent 能追问而不是失忆。
3. **它是业务事实**，不是运行时状态："用户已声明要退哪个订单"和"图跑到第几步"是两类数据。

反面意见也要说清：放 state 更省一张表，且天然随会话销毁。
如果你的判断是"第一版不值得多一张表"，可以退回 state，代价是上面三条。

---

**`refund_requests`**

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | BIGINT PK | |
| `request_no` | VARCHAR(40) UNIQUE | 对外标识 |
| `order_id` | BIGINT FK -> orders.id | |
| `user_id` | BIGINT FK -> users.id | 申请人，便于鉴权与统计 |
| `reason_raw` | VARCHAR(1000) | **原因原文，原样保存不加工**（`B03` 含引号换行也照存） |
| `reason_category` | VARCHAR(32) NULL | 规范化分类，模型产出，`B13` 考的就是否定语义不反转 |
| `amount_cents` | BIGINT | 服务端取自订单，非入参 |
| `status` | VARCHAR(16) | `pending` / `approved` / `rejected` / `refunded` |
| `decided_by` | BIGINT NULL FK -> users.id | 审批人 |
| `decided_at` | DATETIME(6) NULL | |
| `decision_reason` | VARCHAR(500) NULL | 拒绝理由 |
| `executed_at` | DATETIME(6) NULL | |
| `execution_attempts` | INT DEFAULT 0 | 重试计数 |
| `last_error` | VARCHAR(500) NULL | 最近一次失败原因 |
| `active_flag` | TINYINT 生成列 | 见 2.3 |
| `created_at` / `updated_at` | DATETIME(6) | |

索引：`UNIQUE(order_id, active_flag)`、`(user_id, created_at DESC)`、`(status, created_at)`。

---

**`refund_transactions`**（模拟退款流水，只增不改）

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | BIGINT PK | |
| `refund_request_id` | BIGINT **UNIQUE** FK -> refund_requests.id | 幂等核心 |
| `order_id` | BIGINT FK -> orders.id | |
| `amount_cents` | BIGINT | |
| `idempotency_key` | VARCHAR(80) UNIQUE | `refund-{request_no}` |
| `channel` | VARCHAR(16) | `mock` |
| `status` | VARCHAR(16) | `succeeded` |
| `external_ref` | VARCHAR(64) NULL | 模拟渠道单号 |
| `executed_at` | DATETIME(6) | |

### 2.3 三个关键约束（幂等的三道防线）

这是整份设计里最值得讲的部分。

**第一道：同一订单最多一个活跃申请**

`acceptance-cases.md` 的 `E04` 要求"同订单不同请求 ID 并发申请，最多一个有效申请，
**不能仅靠请求幂等键**"。MySQL 不支持部分唯一索引（`WHERE status IN (...)`），
所以用生成列把"活跃"编码进索引：

```sql
active_flag TINYINT GENERATED ALWAYS AS
  (CASE WHEN status IN ('pending','approved') THEN 1 ELSE NULL END) STORED,
UNIQUE KEY uq_order_active_refund (order_id, active_flag)
```

原理：**唯一索引里 NULL 不参与唯一性判断**。已终结的申请
（`rejected` / `refunded`）`active_flag` 为 NULL，可以有任意多条；
只有活跃的才占用 `(order_id, 1)` 这个组合。

为什么不用 `SELECT ... FOR UPDATE` + 应用层判断：那要求**每一条写路径都记得加锁**，
漏一处就漏；唯一约束是绕不过去的。应用层的"先查有没有 pending"只是
省掉一次异常处理的优化，不是保证。

**第二道：同一申请只退一次**

`refund_request_id UNIQUE`。`E03`（同申请并发批准 10 次）只有一个能插入成功，
其余捕获 `IntegrityError` 后**重查并返回既有流水**，对外表现一致。

**第三道：状态迁移守卫**

`UPDATE ... WHERE status = <旧值>` + 检查 `affected_rows`。
`E05`（批准与拒绝并发）只有一个能拿到 `affected_rows == 1`，
另一个收到 `RefundAlreadyDecided`，不会覆盖。

三道防线分别对应三种并发：**跨请求**（同一订单反复申请）、
**同请求重放**（网络重试）、**状态竞争**（审批 vs 拒绝）。

### 2.4 明确不建的两张表

**不建全局 `idempotency_keys` 表。** 很多教程会先上这张表（或 Redis 幂等键），
但这个项目的业务自然键已经够了：

- 提交申请重复 -> 撞 `UNIQUE(order_id, active_flag)` -> 重查返回既有申请（`E09`）
- 审批重复 -> 撞 `refund_request_id UNIQUE` -> 返回既有流水
- 状态重复迁移 -> 撞 `affected_rows == 0` 守卫（`E05`）

**只有当同一个业务操作可以用不同的自然键表达时，才需要独立的幂等键表。**
这里不存在这种情况。少一张表，少一处要与业务事务对齐的一致性风险。

**不建 `approval_records` 审计表。** 审批动作在 `refund_requests` 上已有
`decided_by / decided_at / decision_reason`，第一版没有第二个消费者。
等出现"多次审批尝试""审批意见流"再加。

### 2.5 PostgreSQL 表

LangGraph 的 checkpointer 自己建表，不进 Alembic 迁移，也不用 ORM 建模。
只需要约定它的 `thread_id` 取自 `conversations.conv_no`。

---

## 3. 文件规划

### 3.1 目录树

标 `[新]` 的本次创建，标 `[改]` 的修改已有文件，其余不动。

```
src/supportflow/
├── core/
│   ├── config.py          [改] 增 DATABASE_URL / REFUND_WINDOW_HOURS / POLICY_VERSION
│   ├── enums.py           [新] OrderStatus / RefundStatus / Role / IneligibilityCode
│   ├── errors.py          [新] 业务异常 + 到 HTTP 状态码的映射
│   ├── actor.py           [新] Actor(user_id, user_no, role)，service 的身份入参
│   └── clock.py           [新] utcnow()，全局唯一时间源
├── db/
│   ├── base.py            [新] Base(DeclarativeBase) + TimestampMixin
│   └── session.py         [新] engine / SessionLocal / get_session 依赖
├── models/
│   ├── user.py            [新]
│   ├── order.py           [新]
│   ├── conversation.py    [新] Conversation + ConversationSlot
│   ├── refund.py          [新] RefundRequest + RefundTransaction
│   └── __init__.py        [改] 导出全部模型（autogenerate 要求能 import 到）
├── schemas/
│   ├── order.py           [新] OrderOut
│   ├── refund.py          [新] RefundRequestIn / RefundRequestOut / DecisionIn
│   ├── conversation.py    [新] ConversationOut / MessageIn（④ 步用）
│   └── __init__.py        [改]
├── services/
│   ├── orders.py          [新] get_order_for_user / check_refund_eligibility
│   ├── refunds.py         [新] submit_refund_request / decide_refund
│   ├── conversations.py   [新] create / assert_owner / resolve_slot / set_slot
│   └── __init__.py        [改]
├── api/
│   ├── deps.py            [新] get_current_user / require_admin
│   ├── orders.py          [新] GET /orders/{order_no}
│   ├── refunds.py         [新] POST /refund-requests, GET /refund-requests/{no}
│   ├── admin.py           [新] POST /admin/refund-requests/{no}/decision
│   ├── router.py          [改] 注册新路由
│   └── __init__.py        [改]
├── agent/                 （本步不动）
└── retrieval/             （本步不动）

scripts/seed.py            [新] 确定性种子，接收基准时间参数
alembic/                   [新] alembic init 生成，env.py 指向 models
tests/
├── conftest.py            [新] 事务回滚 fixture + 固定时钟 + 三个 Actor
├── test_orders.py         [新] 只读与越权
├── test_refund_rules.py   [新] 资格判定全分支
├── test_refund_flow.py    [新] 提交 -> 审批 -> 执行 + 幂等
└── test_permissions.py    [新] 伪造身份、跨用户访问
```

### 3.2 几个文件的作用，以及为什么单独一个文件

- **`core/clock.py`** —— 值一个独立文件。`B07/B08`（14 天边界）、
  UTC 统一、`B09`（签收时间在未来）三件事全依赖"现在几点"。
  把它变成显式依赖，测试才能冻结时间；散落的 `datetime.now()` 会让边界用例没法稳定断言。
  它和 `scripts/seed.py` 的"基准时间参数"是两回事：前者是运行时时钟，后者是数据构造基准。

- **`core/actor.py`** —— `service` 只认 `Actor`，不认 `User` ORM 对象。三个好处：
  单测不用造 ORM 对象与 session；避开 detached instance 与懒加载；
  未来换 JWT 只改 `api/deps.py`。

- **`core/errors.py`** —— 业务异常集中定义，`api` 层统一转 HTTP。
  好处是 `services` 不 import FastAPI，纯业务代码可单测。

- **`api/admin.py` 独立** —— 管理员接口的鉴权要求与客户接口完全不同。
  混在一个文件里最容易漏加 `require_admin`（`D06` 就是这么漏出来的）。

### 3.3 不建 `repositories/` 层

`services` 就是用例边界，里面直接写 SQLAlchemy 查询。
再插一层 `repositories` 在第一版只会变成 `def get(...)` 的转发，
多一层跳转、少一层可读性，还多一处要对着改的地方。

**什么时候该引入**：同一个查询被 3 个以上 service 复用，
或需要为它加缓存 / 换 ORM / 单独做数据权限时。

反过来，`services` 有一条硬纪律：**函数签名收 `session`，不 commit、不返回 session。**

### 3.4 事务边界

`db/session.py` 的 `get_session` 依赖**不自动 commit**。
service 只 `flush()`，提交由 API 层的 `with session.begin()` 决定。

理由：一个请求可能串多个 service（比如"提交申请 + 更新会话槽位"）。
若每个 service 各自 commit，"申请建了但槽位没更新"就会成为可能；
包在一个事务里才能整体原子。测试侧也受益——回滚式 fixture 更容易写。

### 3.5 落地顺序（拓扑序）

```
1  core/enums.py, core/errors.py, core/clock.py, core/actor.py      无依赖
2  core/config.py 加 DATABASE_URL / REFUND_WINDOW_HOURS             无依赖
3  db/base.py -> models/*                                           只依赖 base
4  alembic init + 第一个迁移                                        此时表才真正建出来
5  scripts/seed.py                                                  迁移之后才能灌数据
6  db/session.py                                                    可早于 3、4，无依赖
7  services/orders.py（只读）                                        <- M1
8  api/deps.py + api/orders.py + schemas/order.py                    <- M1 收口
9  services/refunds.py + schemas/refund.py                           <- M2
10 api/refunds.py                                                    <- M2 收口
11 api/admin.py                                                      <- M3
12 Agent 的 tool 包装                                                <- M4
```

`db/session.py` 与 `models/` 谁先都行（模型只依赖 `Base`，引擎不依赖模型）。
**唯一有严格顺序的是：迁移必须在模型之后，种子必须在迁移之后。**

### 3.6 四个里程碑

| 里程碑 | 内容 | 怎么算完成 |
| --- | --- | --- |
| **M1 只读闭环** | models + db + alembic + seed + orders service + `GET /orders/{no}` | U1 查 A1001 得 29900 分；U2 查 A1001 与查不存在的订单返回相同响应 |
| **M2 规则闭环** | refunds service + `POST /refund-requests` | 资格判定的每个分支都有断言：未支付 / 未签收 / 超期 / 边界 14 天 / 14 天+1 秒 / 未来说明异常 / 已退款 / 已有活跃申请 |
| **M3 审批与幂等** | `api/admin.py` | 并发批准 10 次只有 1 条流水；批准与拒绝并发只有一方成功；重复审批返回既有结果 |
| **M4 Agent 接入** | 把 service 包成 tool | tool 的入参 schema 里没有 `user_id`、没有 `amount_cents` |

M1 一天能到，而且能立刻用 curl 演示。**建议 M1 做完就先停下看看**，
再决定后续细节，避免一次铺开。

### 3.7 种子数据要覆盖的边界

`scripts/seed.py` 接一个基准时间参数（默认当前 UTC），所有时间相对它算偏移：

| 订单 | 相对签收 | 状态 | 预期 |
| --- | --- | --- | --- |
| A1001 | -10 天 | paid+delivered | 通过，29900 分 |
| A1002 | -15 天 | paid+delivered | `WINDOW_EXPIRED` |
| A1003 | 无 | created（未支付） | `NOT_PAID` |
| A1004 | -10 天 | refunded | `ALREADY_REFUNDED` |
| A1005 | -10 天 | paid+delivered | 通过（供 `A05` 改口用） |
| B1001 | -10 天 | paid+delivered | 属 U2，U1 访问得 `ORDER_NOT_FOUND` |

再加两条例外样本，`B07/B08` 直接依赖它们：**恰好 14 天整**、**14 天加 1 秒**。

**不要把签收时间写死成日期。** 今天跑 `B07` 是绿的，两周后全部超期变红。
写成相对基准的偏移，既能复现，也不会随时间腐烂。

---

## 4. 需要你拍板的四件事

1. **`conversation_slots` 放 MySQL 还是 LangGraph state**（见 2.2 末尾的三个理由与反面意见）。
   我推荐 MySQL，但这是可逆的，代价是多一张表。
2. **是否现在就拆 `order_items`**。我推荐第一版不拆，但要在文档里写明是有意简化。
3. **认证方式**。第一版建议固定 header 切身份（如 `X-Actor: U1`），
   但必须做到"身份只从 header 来，schema 里不存在 `user_id` 字段"。
   所有请求 schema 加 `extra="forbid"`，让伪造字段直接 422 而不是被静默忽略。
4. **会话消息历史是否要在 MySQL 冗余一份**。我推荐不冗余，
   MySQL 只存会话元数据与归属，消息正文交给 checkpoint。
   代价是 PostgreSQL 挂掉时读不到历史。

---

## 5. 这一版明确不做

- 不做多 Agent、不做 MCP（自闭环单体应用，进程内直接调 service）。
- 不做 YAML 流程引擎（流程只有一条，且由你自己改，收益拿不到）。
- 不建 `repositories` 层、不建全局幂等键表、不建审批审计表。
- 不做完整认证（JWT / 注册 / 密码）、不做 Docker、暂不接 Qdrant 或 Milvus
  （检索是第 ⑤ 步的事，本版不写一行检索代码）。
