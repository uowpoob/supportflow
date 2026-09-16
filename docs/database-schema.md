# 第一版业务表结构

## 范围与约定

用户端通过对话调用工具，管理端通过 HTTP 接口查看订单、审批退款；两者共用业务层。
MySQL 保存业务事实和会话归属。PostgreSQL 的消息与 checkpoint 表在接入 LangGraph 时由对应组件管理，本步不定义图状态。

初始七张业务表对应迁移 `0001_initial`；认证会话表由 `0002_auth_sessions` 新增。[MySQL DDL](schema-v1.sql) 仅作为初始七张表的结构参考，当前结构以 ORM 和迁移为准。正式落库使用 [Alembic 迁移](database-migrations.md)，目标 MySQL 8.0.16+（支持强制 CHECK 约束）。

- 主键除会话 UUID 外为自增 BIGINT；所有表包含 `created_at`、`updated_at`，使用 UTC、微秒精度。
- 时间默认值、更新时间和 UUID 由 ORM 写入，直接执行 SQL 时必须自行提供。状态存储小写字符串。
- 金额单位为分，使用整数；第一版仅 CNY、整单全额模拟退款。
- 外键禁止级联删除；用户使用 `is_active` 停用，保留订单和审批历史。
- 第一版不做商品管理，订单明细保存下单时的商品快照。

## 表与字段

以下各表省略公共主键和创建、更新时间；完整类型、空值与索引见 DDL。

| 表 / 实体 | 字段 | 用途 |
| --- | --- | --- |
| `users` / User | username（唯一）、password_hash、role、is_active | 用户与管理员共用账号表；只保存密码哈希 |
| `auth_sessions` / AuthSession | token_hash（唯一，64 字符）、user_id（外键及索引）、expires_at（索引） | 登录凭证的 SHA-256 摘要及 UTC 过期时间；同一用户可有多个登录会话 |
| `orders` / Order | order_no（唯一）、user_id、paid_amount_cents、payment_status、fulfillment_status、paid_at、shipped_at、delivered_at、tracking_no | 订单归属、支付和履约事实；时间及物流单号可为空 |
| `order_items` / OrderItem | order_id、product_code、product_name、product_model、quantity、unit_price_cents | 一单多商品；型号可为空，单价是商品快照，退款金额取订单实付 |
| `conversations` / Conversation | id（UUID）、user_id、title | 会话归属与列表；id 同时用作 checkpoint thread_id |
| `refund_requests` / RefundRequest | request_key（唯一）、order_id、conversation_id、amount_cents、reason_original、reason_category、status、active_order_id | 退款申请；原因分类可为空，原文必须保存；active_order_id 为数据库生成列 |
| `refund_approvals` / RefundApproval | refund_request_id（唯一）、admin_id、decision、comment | 每个申请最多一次最终审批；备注可为空，创建时间即审批时间 |
| `refund_records` / RefundRecord | refund_request_id（唯一）、refund_no（唯一）、amount_cents、status、attempt_count、last_error、succeeded_at | 模拟执行流水；失败重试更新同一条，错误和成功时间可为空 |

关系：用户拥有多张订单、多个会话；订单有多个明细和历史退款申请；申请属于一次会话，最多对应一条最终审批和一条执行流水。
申请的客户从订单归属获取，不重复存储 user_id；业务层必须验证订单与会话属于同一登录用户。

## 状态

认证会话与 `conversations` 中的售后对话不同。认证会话包含公共的 id、created_at、updated_at，不保存凭证原文。
登录逻辑已生成高强度随机凭证，计算 SHA-256 摘要后写入本表；密码仍使用独立的密码哈希算法，详见 [登录流程](login-flow.md)。
认证时必须检查 `expires_at > 当前 UTC 时间` 和用户启用状态；数据库不会自动使过期记录失效或删除记录。
退出时计划删除当前凭证对应的会话记录。当前已接入登录写入及 Cookie 下发，尚未实现后续请求的身份校验和退出接口。

| 字段 | 可用值 / 流转 |
| --- | --- |
| 用户角色 | `customer`、`admin` |
| 支付状态 | `unpaid → paid → refunded` |
| 履约状态 | `unshipped → shipped → delivered` |
| 申请状态 | `pending → approved → refunded`，或 `pending → rejected` |
| 审批决定 | `approved`、`rejected` |
| 流水状态 | `processing → succeeded / failed`；失败可回到 `processing` 重试 |

执行失败时申请仍为 `approved`，流水标记 `failed`，不会把订单标记已退款。
已拒绝的申请不重新打开，用户可发起新申请。会话暂不增加无实际需求的状态字段。

## 数据库约束与业务层职责

数据库已定义：

- 用户名、订单号、申请操作 ID 唯一；外键确保关联记录存在。
- 同订单处于 pending、approved 或 refunded 的申请最多一条：生成列 active_order_id 加唯一约束；rejected 对应 NULL，可保留多次拒绝历史。
- 每个申请最多一条审批和一条执行流水，抵御重复写入。
- 金额非负（退款为正）、数量为正、重试次数非负、原因非空，以及状态值约束。

后续业务层必须实现（实体本身不等于这些功能已完成）：

- 认证身份、角色与归属校验；禁用用户不能登录；密码安全哈希。
- 已支付且签收不超过 14 天等资格校验；完整空白字符校验；CNY 限制。
- 申请金额从订单实付取得；执行时复核订单归属、金额和状态。
- 审批时锁定申请或使用带旧状态条件的更新，审批记录与申请状态同事务提交。
- 模拟退款流水成功、申请 refunded、订单 refunded 在同一 MySQL 事务中提交。
- request_key 在同一操作重试时保持稳定，并核对既有请求归属，不由模型随意生成。
- 每次访问 checkpoint 前验证会话归属，更新会话活动时间；跨库恢复以 MySQL 为准。

数据库枚举约束只限制合法值，不自动保证状态流转、角色或跨表金额一致。
