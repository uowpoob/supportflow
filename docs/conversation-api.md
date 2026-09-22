# 客户会话接口

会话管理在 MySQL，消息与图状态保存在现有 LangGraph checkpointer。
服务端创建会话时由 `Conversation` ORM 默认值生成 UUID v4；
同一会话始终满足 `conversation_id == thread_id`，使用带连字符的 UUID 字符串，
不会为每条消息新建 thread_id。现有模型已支持，无需数据库迁移。

四个接口位于 `/customer/conversations`，均要求客户登录 Cookie。
前端通过现有代理访问时加 `/api` 前缀。

## 创建会话

`POST /customer/conversations`

请求体可以省略或传 `{}`，默认标题为“新会话”；也可以指定标题：

```json
{"title": "耳机使用咨询"}
```

标题去除首尾空白后必须为 1～200 个字符。不接受 `id`、`user_id`、`thread_id`
等额外字段。服务端先提交 MySQL 会话记录，返回 HTTP 201：

```json
{
  "code": "200",
  "message": "ok",
  "data": {
    "id": "b9c4e5ac-2dab-4bb9-8bc2-0c1ec5a08ae4",
    "title": "耳机使用咨询",
    "created_at": "2026-09-22T08:00:00.000Z",
    "updated_at": "2026-09-22T08:00:00.000Z"
  }
}
```

以上 UUID 和时间是格式示例。响应信封沿用项目的 `Success`（`code="200"`）；
HTTP 状态码 201 表示会话已创建。创建空会话不会调用模型或预先生成聊天消息。

## 会话列表

`GET /customer/conversations?offset=0&limit=10`

仅返回当前用户的会话，按 `updated_at` 倒序、ID 倒序排列。
`data` 包含 `items`、`total`、`offset`、`limit`。`offset >= 0`，`limit` 为 1～100。
发送消息时更新最近活动时间；已有退款业务创建的 UUID 会话也会出现在列表中。

## 历史消息

`GET /customer/conversations/{conversation_id}/messages?offset=0&limit=50`

路径参数必须是 UUID。先在 MySQL 中按会话 ID 和当前用户 ID 查询归属，
校验通过后才读取该 UUID 对应的 checkpoint。不是本人的会话与不存在的会话统一返回 404。

`data` 包含 `conversation_id`、`items`、`total`、`offset`、`limit`。
消息按对话顺序排列，分页针对过滤后的可展示消息；新会话没有 checkpoint 时返回空列表。
每条消息结构为：

```json
{"id": "消息ID", "role": "user", "content": "你好"}
```

`role` 为 `user` 或 `assistant`。不暴露系统提示、工具调用参数、工具返回或推理内容块。
当前从完整 checkpoint 读取消息，再在内存中分页，适用于当前的小规模对话。

## 发送消息

`POST /customer/conversations/{conversation_id}/messages`

```json
{"content": "索尼 WH-1000XM5 怎么使用有线模式？"}
```

只接收一条新的用户消息，去除首尾空白后必须为 1～8000 个字符，拒绝额外字段。
客户端不提交历史消息、角色、模型参数或图状态。

服务启动时构建并复用图，沿用已有 checkpointer；每次请求单独提供
`SupportContext(user_id, conversation_id, db)`，其中身份来自认证态，
MySQL Session 由本次请求持有。图通过同一个 UUID 恢复历史。

这是非流式接口，等待本轮完成后返回 HTTP 200，`data` 包含：

- `conversation_id`：当前 UUID。
- `messages`：本轮新增的可展示消息，包括用户消息和助手答复，结构同历史接口。
- `retrieval_status`：本轮 `not_requested` / `ready` / `empty` / `unavailable`。
- `retrieved_sources`：本轮召回片段的文档 ID、片段 ID、标题、来源、章节及排序分数。
  这是检索候选来源列表，不表示助手实际引用了每个片段；业务对话通常为空列表。

## 错误与当前边界

| HTTP 状态码 | 含义 |
| --- | --- |
| 401 | 未登录或会话失效 |
| 403 | 当前角色不是客户 |
| 404 | 会话不存在或不属于当前客户 |
| 409 | 同一服务进程中，该会话已有一轮对话正在执行 |
| 422 | 非法 UUID、分页参数、空白/超长文本或额外请求字段 |
| 502 | 图或模型执行未完成；响应不暴露底层异常内容 |
| 503 | 对话服务未就绪或 checkpoint 读取失败 |

错误响应使用现有 FastAPI `detail` 格式。图失败不会自动重跑，因为此前的业务工具可能已提交
退款申请；请先查看历史、订单和退款状态，再决定是否重新发送。MySQL 业务提交与 PostgreSQL
checkpoint 不构成跨库原子事务，HTTP 失败不代表所有业务操作都已回滚。

当前只有单进程的同会话并发保护，尚无跨进程运行锁、请求幂等键、SSE 或断流恢复协议；
这一阶段按单个后端进程使用。重复发送是新的用户消息，不保证复用上次执行。
前端聊天交互尚未接入，现有列表会开始显示真实会话。

配置 `LANGGRAPH_PG_DSN` 时消息持久化到 PostgreSQL；未配置时沿用内存回退，服务重启会丢失消息，
MySQL 中的会话列表仍在。原手动脚本固定 `test-1` 的 checkpoint 不会自动迁移进新的 UUID 会话。

本次仅完成实现和静态阅读，按用户要求未运行测试或接口联调。
