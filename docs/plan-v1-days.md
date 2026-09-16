# SupportFlow 逐日开发计划（第③–⑧步，15 天）

> 本文件是施工排期，不替代 `project-scope.md`（范围）、`acceptance-cases.md`（验收用例）、
> `design-v1.md`（文件与表设计）。每天的"完成判据"都是可验证的硬指标，不是"大概做完了"。
> 节奏假设：每天 3–4 小时。第 7、13 天是天然缓冲，用来吸收前面拖期。

---

## 0. 开工体检（2026-09-15 实测）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| MySQL | ✅ 可用 | 实测连通（9/15）。⚠️ `supportflow.db.check` **模块并不存在**（历史记录里的引用有误，已核实目录），验证请改用 `python -m supportflow.db.seed_users` 或直连查询 |
| ORM 实体 | ✅ 已写 | `models/entities.py` 七张表 + `models/enums.py`，仅离线约束测试，**未建表** |
| 引擎与会话 | ✅ 已写 | `db/session.py`（asyncmy + `async_sessionmaker` + `get_db`） |
| Alembic | ✅ 已装 | `alembic 1.20.0`（9/15）。迁移尚未初始化，表还没真正建出来，种子无处可落 |
| pytest | ✅ 已装 | `pytest 9.1.1` + `pytest-asyncio 1.4.0`（dev 组，9/15）。现有 `tests/test_models.py` 已能被收集：5 passed |
| Milvus | ⚠️ 已部署未开机 | 实例在 `D:\milvus`，compose **未写 restart 策略**，每天开工先 `docker compose up -d` |
| PostgreSQL | ⚠️ 容器已建、未运行 | 容器 **`langgraph-postgres`**（镜像 `postgres:16`），`5432:5432`，库 `langgraph_db`、用户 `langgraph_user`；实测状态 `Exited (255)`，开工先 `docker start langgraph-postgres` |
| Embedding | ✅ 已定且已通 | **`text-embedding-v4`**（阿里云百炼，走 OpenAI 兼容模式）。取 **1024 维**（可选 2048/1536/1024/768/512/256/128/64），单行 **8192 Token**、单次最多 **10 条**。配置已写入 `.env` 与 `core/config.py`，2026-09-15 实测返回 200 |
| Reranker | ✅ 已定且已通 | **`gte-rerank-v2`**（阿里云百炼，走 **DashScope 原生接口**，非兼容模式）。实测 **通用域名即可调用，不需要官方文档里的 `{WorkspaceId}.cn-beijing.maas` 域名**；复用同一个 `DASHSCOPE_API_KEY`。2026-09-15 实测返回 200 且排序正确 |
| 冗余依赖 | ✅ 已清理 | `deepagents` 已移出 `pyproject.toml`，`uv lock` + `sync` 连带卸掉 14 个包（anthropic / google-genai / google-auth / cryptography / wcmatch 等），`pytest -q` 仍全绿 |
| entry point | ✅ 实测正常 | `[project.scripts] supportflow = "supportflow:main"` 里的 `supportflow` 是**包**，`main` 定义在 `__init__.py`（签名 `() -> None`）。实跑 `.venv/Scripts/supportflow.exe`，`/health` 返回 200 —— 之前"写错"的判断是错的 |
| 会话存储 | ✅ 已定 | 消息正文与图状态进 **PostgreSQL**；MySQL 的 `conversations` 只留会话 id + 归属，归属校验先走 MySQL 再读 checkpoint |

已装：sqlalchemy 2.0.53 / asyncmy 0.2.14 / langgraph 1.2.11 / langgraph-checkpoint 4.2.0 /
langsmith 0.12.4 / langchain 1.4.0 / fastapi 0.141.1 / python-dotenv 1.2.3 /
alembic 1.20.0 / pytest 9.1.1 / pytest-asyncio 1.4.0。

---

## 第一段｜第③步 数据库与业务 API（Day1–Day7）→ M1 / M2 / M3

**本段完成判据：B 类 13 条全绿 + D01/D02 通过 + 一行 Agent 代码都没有。**

### Day 1｜9/15（周二）依赖与骨架

- **目标**：把地基铺平，不写业务逻辑。
- **已完成（9/15）**：`deepagents` 已从 `pyproject.toml` 移除，`uv lock` + `uv sync --locked` 后
  连带卸掉 14 个包，`pytest -q` 仍全绿。entry point 用户要求先不动，实测它本来就是好的（见体检表）。
  **依赖已装齐**：`alembic 1.20.0`（主依赖，部署时要在容器里跑 `upgrade head`）、
  `pytest 9.1.1` + `pytest-asyncio 1.4.0`（dev 组，`uv sync --no-dev` 不会进生产镜像），
  `pytest -q` 已能收集现有测试（5 passed）。
- **产出**：`core/errors.py`（业务异常 + 到 HTTP 状态码的映射）、`core/clock.py`（`utcnow()` 唯一时间源）、
  `core/actor.py`（`Actor(user_id, username, role)` —— 注意 `users` 表没有 `user_no` 这一列，
  身份字段就是 `id` / `username` / `role`），
  `core/config.py` 补 `REFUND_WINDOW_HOURS`、`POLICY_VERSION` 与 PG 连接四项
  （**DASHSCOPE 与 embedding 相关四项已于 9/15 提前写入 `.env` 与 `config.py`**）。
- **判据**：`uv sync --locked` 通过；`python -m pytest -q` 全绿（当前 5 passed）；
  `from supportflow.core.actor import Actor` 可用；`import supportflow.agent.llm` 不再自动发模型请求。
- **坑**：
  - `agent/llm.py` 的 `client.invoke("hello")` 写在模块顶层，import 即调模型 —— 接 LangGraph 前必须挪进函数。
  - `errors.py` 的存在意义是让 `services/` 不 import FastAPI，保持纯业务可单测。

### 9/15 试过又回退：登录与页面路由（**已取消代写，改由用户主导**）

- **背景**：9/15 用户提到"登录后按角色跳到 `/user` 或 `/admin`"，我把它整段写完并实测通过；
  用户随后要求撤回 —— **他想自己一步步写，只要引导、不要代写**。
- **处理**：新增的 9 个源文件与 4 个模板已删除；`api/router.py`、`main.py`、`core/config.py`
  的改动已还原（前两个 `git checkout` 回到 `Init` 提交，`config.py` 手工摘掉 `SESSION_*` 两项）。
  草稿完整备份在 `.workbuddy/backup/2026-09-15-login-draft/`，需要时可整段取回。
- **遗留项（待用户决定）**：
  - `pyproject.toml` / `uv.lock` 里仍留着当时装的 4 个依赖：`jinja2`、`bcrypt`、`itsdangerous`、
    `python-multipart`（登录与模板渲染本来就要用，是否保留由用户定）。
  - MySQL `users` 表里有 2 行当时造的演示账号（`admin` / `customer`），需不需要删由用户定。
- **结论**：**登录与页面路由不再当作原排期外的插单任务**，它属于第③步"身份与订单接口"的一部分
  （见 Day 5），届时按"用户主导、逐文件讲解"的方式推进。
- **顺手留下的可用结论（与代码无关，仍然成立）**：
  - `users` 表没有 `user_no`，身份字段就是 `id` / `username` / `role`。
  - **本机有 `http_proxy=http://127.0.0.1:1420`**，httpx 默认 `trust_env=True` 会把 localhost 请求
    也交给代理并返回 404；测本机服务要 `httpx.Client(trust_env=False)`，curl 不受影响。
  - 8000 端口同时跑多个 `supportflow.exe` 时请求被随机分发，表现为"同一路径一会儿 200 一会儿 404"；
    重测前先确认只有一个 LISTENING。


### Day 2｜9/16（周三）Alembic 第一个迁移：表真正建出来

- **目标**：数据库从"文档里的设计"变成"真实的表"。
- **产出**：`alembic/`（`alembic init -t async alembic`，复用 asyncmy，不必再装 pymysql）、
  `alembic/env.py` 指向 `Base.metadata`、`alembic/versions/0001_*.py`。
- **判据**：`alembic upgrade head` 后 MySQL 里 7 张表齐备；`alembic downgrade base` 能干净回退；
  生成的 DDL 与 `docs/schema-v1.sql` 逐列对齐。
- **坑（第一次迁移最容易翻车的地方）**：
  - 生成列 `active_order_id`：`CASE WHEN status IN ('pending','approved','refunded') THEN order_id END`
    必须写成 **STORED**，且 `UNIQUE(order_id, active_order_id)` 的语义靠"唯一索引里 NULL 不参与判重"成立。
  - MySQL 8.0.16+ 才真正执行 `CHECK`；低版本会被静默忽略，要确认服务端版本。
  - `DATETIME(6)` 而非 `TIMESTAMP`（后者按会话时区转换且 2038 溢出）。
  - `alembic/env.py` 必须能 import 到全部模型，否则 autogenerate 产出空迁移。

### Day 3｜9/17（周四）确定性种子 + 测试夹具

- **目标**：让每条用例都有可复现的初始数据。
- **产出**：`scripts/seed.py`（接 `--base-time` 参数，默认当前 UTC，所有时间按偏移算）、
  `tests/conftest.py`（事务回滚 fixture + 冻结时钟 + U1/U2/M1 三个 Actor）、`tests/test_seed.py`。
- **判据**：连跑两次 seed 结果一致；改 `--base-time` 所有时间整体平移；
  A1001 = 29900 分 / A1002 超期 / A1003 未支付 / A1004 已退款 / A1005 正常（供 A05 改口用）/
  B1001 属 U2 全部落库；**额外两条边界样本**：恰好 14×24h 整、14×24h + 1 秒。
- **坑**：**不要把签收时间写死成日期** —— 今天绿的用例两周后全变红。必须相对基准时间偏移。

### Day 4｜9/18（周五）资格判定 service（本段最核心的一天）

- **目标**：把退款规则写成一个确定、可单测的纯业务函数。
- **产出**：`services/orders.py`（`get_order_for_user`、`check_refund_eligibility`）、
  `core/errors.py` 补齐错误码、`tests/test_refund_rules.py`。
- **判据**：九条分支逐条断言全绿 —— 归属 → 未支付 → 未签收 → 已退款 → 签收在未来 →
  超期 → 已有活跃申请 → 合格；覆盖 B04–B10。
- **坑（顺序本身就是设计，不能打乱）**：
  1. 归属检查**必须最先**，否则"未支付""超期"的报错差异会成为"订单是否存在"的旁路信道（D01）。
  2. `delta < 0`（签收在未来）单独一个错误码：B09 要求"报告数据异常"而不是普通拒绝。
  3. 用 `14 * 24h` 的**秒级连续时间比较**，不是天数差 —— B07 恰好 14 天要通过、B08 加 1 秒要拒绝。
  4. **可预期的业务分支返回结果，不可预期的违规抛异常**：不合格要交给模型解释，
     越权/不存在用异常（不进模型可见上下文）。

### Day 5｜9/19（周六）身份依赖 + 订单只读 API → M1

- **目标**：打通第一个闭环，能立刻 curl 演示。
- **产出**：`api/deps.py`（`get_current_user` / `require_admin`，第一版用固定 header `X-Actor: U1`）、
  `schemas/order.py`（`extra="forbid"`）、`api/orders.py`、`api/router.py` 注册、
  `tests/test_orders.py`、`tests/test_permissions.py`。
- **判据（M1）**：U1 查 A1001 得 29900 分；**U2 查 A1001 与查 A9999 返回完全相同的响应**；
  请求体里塞 `user_id` 直接 422 而不是被静默忽略。
- **坑**：
  - 身份**只从 header 来**，任何请求 schema 里都不存在 `user_id` 字段。
  - "不是你的"与"不存在"在 service 层就抹平成同一个 `OrderNotFound`，不靠提示词约束模型别说漏。
  - 响应模型**不能用 ORM 对象直接当**（会泄露内部字段与分单位金额，还会踩懒加载）。

### Day 6｜9/20（周日）退款申请 service + API → M2

- **产出**：`services/refunds.py`（`submit_refund_request`）、`schemas/refund.py`、
  `api/refunds.py`（提交 + 查询）、`tests/test_refund_flow.py`。
- **判据（M2）**：B01/B02/B03/B11/B12/B13 全绿；同订单重复提交或并发提交只产生 1 条 pending；
  原因含引号、换行、SQL 字符串也原样落库且不执行 SQL；已有 pending 时返回既有申请而不是新增。
- **坑**：
  - **金额永远从订单实付取**，入参里没有 `amount_cents` 这个参数（签名层面就不给填）。
  - 提交前**内部重新做一次资格检查**，不信模型上一轮得到的结论。
  - 事务边界：service 只 `flush()` 不 `commit()`，提交由 API 层 `with session.begin()` 决定 ——
    一个请求串多个 service（提交申请 + 更新会话槽位）时才能整体原子。

### Day 7｜9/21（周一）管理员审批 + 幂等三道防线 → M3，③ 收口

- **产出**：`api/admin.py`（独立文件，鉴权要求与客户接口完全不同，混写最容易漏加 `require_admin`）、
  `services/refunds.py#decide_refund`、`tests/test_admin.py`。
- **判据（M3 + ③ 完成）**：
  - E01/E02（正常申请后 MySQL 为 pending、流水 0 条；拒绝后 rejected、流水 0 条）
  - E03 并发批准 10 次**只有 1 条流水**
  - E04 同订单不同请求 ID 并发申请**最多一个有效申请**（不能只靠请求幂等键）
  - E05 批准与拒绝并发**只有一方成功**，不覆盖
  - D06 客户调审批接口 → 403 且**不写任何审批记录**
- **坑（幂等三道防线，别退化成应用层判断）**：
  - 状态迁移一律 `UPDATE ... WHERE status = <期望旧值>` + 检查 `affected_rows`，
    不做"先 SELECT 判断再 UPDATE"（并发下双写）。
  - 审批记录、申请状态、退款流水、订单状态**同一个 MySQL 事务**提交，要么都成要么都不成。
  - 流水撞唯一约束时**捕获后重查并返回既有流水**，对外表现一致。

---

## 第二段｜第④步 最小 Agent（Day8–Day9）→ M4

### Day 8｜9/22（周二）LangGraph 单图 + tool 包装

- **产出**：`agent/state.py`、`agent/graph.py`、`agent/nodes.py`、`agent/prompts/`、`agent/tools.py`。
- **判据**：意图识别跑通四类（`order_query` / `policy_question` / `refund_request` / `refund_status`）；
  **tool 入参 schema 里没有 `user_id`、没有 `amount_cents`**（用断言锁死，不靠提示词）；
  身份经 LangGraph 的 config/context 注入到 tool。
- **坑**：
  - 图形态：一张图（意图 → 决策·工具调用 → 回答生成）+ 挂在决策节点下的检索子图；
    决策到工具用 **ToolNode + 循环边 + 调用上限**。
  - 不做多 Agent：业务流线性，拆分的代价全打在 P95 延迟、token 成本、端到端成功率上。

### Day 9｜9/23（周三）会话与消息 API + A 类用例

- **产出**：`services/conversations.py`、`api/conversations.py`（创建会话 + `POST /conversations/{no}/messages` + SSE）、
  槽位存储、`tests/test_agent_intent.py`。
- **判据**：A01–A12 通过 —— 含 A05（改口换订单不复用旧单）、A06（指代不明要追问）、
  A07（用本会话已查订单）、A08（插问政策后保留已收集信息不重复建单）、A11（空白/表情要澄清且不动写工具）；
  D03/D04 通过（**读 checkpoint 之前**先做 MySQL 归属校验）。
- **存储归属（9/15 已定）**：**消息正文与图状态放 PostgreSQL**，MySQL 的 `conversations` 表只保留
  会话 id、归属（`user_id`）、标题与时间。顺序必须是"先 MySQL 校验归属 → 再读 PG checkpoint"。
  代价：PG 挂了读不到历史（E12 要按"明确报错、不静默新建上下文"处理）。
- **仍待拍板：会话槽位（`current_order_no` 这类）放哪。** 若坚持"MySQL 只记 id"，槽位更该跟着进
  图 state，但那样 D04（新会话不翻旧账）与 E12（PG 挂掉后仍能追问）要多写一层处理。
- **坑**：`conversation_id` 同时是 PG checkpoint 的 `thread_id`，所以"U2 猜 U1 的会话 ID"只是
  一次 MySQL 查询就能拒掉。

---

## 第三段｜第⑤步 知识检索（Day10–Day11）

### Day 10｜9/24（周四）政策源版本化 + Milvus 索引

- **产出**：`policies/`（版本化政策源，含旧版、不同商品、重复、冲突、恶意片段）、
  `retrieval/chunking.py`、`retrieval/index.py`（建集合 + 稠密向量 + BM25 稀疏 + 元数据）。
- **判据**：`docker compose up -d` 起 Milvus 后，建索引脚本可重复执行（先 drop 再建）；
  按 `version` / `product_model` 过滤生效。
- **坑（全部已实测，写在 `D:\milvus\README.md`）**：
  - `hybrid_search` 顶层的 `filter=` 会被**静默忽略**，过滤必须挂在每个 `AnnSearchRequest` 的 `expr=` 上。
    政策版本过滤失效属于静默漏数据，必须有断言防回归。
  - 建集合时 `SPARSE_FLOAT_VECTOR` 字段要先声明，BM25 function 才有输出目标。
  - `pymilvus` 3.0 命中项取分用 `hit['distance']`，不是 `hit['score']`。
  - 中文分词**不可加自定义词典**（参数被接受但静默无效）；要精确控制词项只能客户端自算稀疏向量。
  - **embedding 已定（9/15）**：**`text-embedding-v4`**（Qwen3-Embedding 系列），
    `base_url = https://dashscope.aliyuncs.com/compatible-mode/v1`，
    HTTP 直调 `POST {base}/embeddings`（SDK 时 base_url 不带 `/embeddings`）。
    维度取 **1024**（可选 2048/1536/1024/768/512/256/128/64），Milvus 集合的 `dim` 必须等于它。
    单行 **8192 Token**、**单次最多 10 条** —— 建索引脚本要按 10 条一批切分。
    单价 0.0005 元/千 token，免费额度 100 万 token（开通后 90 天内）。
    实测：走 settings 调用返回 200、维度 1024。
  - **为什么不用之前那个多模态模型**（官方文档明确写的）：`tongyi-embedding-vision-*` 与
    `qwen3-vl-embedding` 等**多模态 Embedding 不支持 OpenAI 兼容接口**，必须走原生
    `/api/v1/services/embeddings/multimodal-embedding`（`dashscope` SDK）。
    纯文本政策场景用 v4 更省事，且单行 8192 Token 远比多模态的 1024 宽裕。
  - **兼容模式的已知边界**：不支持稀疏向量输出 —— 传 `output_type=sparse` 会返回 200
    但 embedding 为空。本项目**不受影响**：Milvus 的 BM25 是服务端 function
    （`enable_analyzer` + BM25 function），稀疏向量由 Milvus 自己生成，不需客户端计算。
  - **reranker 已定（9/15）**：**`gte-rerank-v2`**，与 embedding 同平台、复用 `DASHSCOPE_API_KEY`。
    与 embedding 的**关键差异是端点**：embedding 走兼容模式
    `dashscope.aliyuncs.com/compatible-mode/v1/embeddings`，而 rerank **没有兼容模式**，
    走原生接口 `dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank`。
    官方文档写的是 `{WorkspaceId}.cn-beijing.maas.aliyuncs.com` 域名，**实测通用域名直接可用，
    不需要 WorkspaceId**（这省掉了从控制台找业务空间 ID 的一步）。
    请求体结构与 embedding 不同：`{"model", "input": {"query", "documents"}, "parameters": {"top_n", "return_documents"}}`，
    响应取 `output.results[].relevance_score`（降序）。实测样例：query"退款必须由谁发起" →
    "退款申请需由订单归属客户本人发起" 0.83 排第一，"14 天退款" 0.15 排第二，排序正确。
    另注：`qwen3-rerank` 走 `/compatible-api/v1/reranks`，请求体是另一套（扁平结构），
    `qwen3-vl-rerank` 支持图片/视频查询 —— 都留作备选，本项目用不上。
  - **Day11 第一件事**：先用 5–10 条真实政策问题跑通 `retrieval/rerank.py` 的
    单条调用（含超时与重试），再接入 Milvus 候选集，**不要一上来就串全链路**。

### Day 11｜9/25（周五）检索子图 + 三档消融 + C 类

- **产出**：`retrieval/rerank.py`、`retrieval/graph.py`（检索子图）、`tests/test_retrieval.py`、
  `docs/retrieval-report.md`（三档对比数字）。
- **判据**：C01–C12 通过；同一冻结查询集上产出 **纯向量 / 混合 RRF / 混合 + 重排** 三档的
  Recall@5、耗时与失败样例（F06）；回答附文档、条款、版本，无依据时追问或转人工。
- **坑**：C11 是陷阱题 —— "有引用但不支持结论"仍要判为无依据，不能因为有引用就通过；
  C07 两份同优先级证据冲突时要明示冲突并转人工，不随意选结论。

---

## 第四段｜第⑥步 审批与恢复（Day12–Day13）

### Day 12｜9/26（周六）PostgreSQL checkpointer + interrupt / resume

- **产出现状（9/15 实测）**：容器 **`langgraph-postgres`** 已经建好 —— 镜像 `postgres:16`，端口
  `5432:5432`，库 `langgraph_db`，用户 `langgraph_user`，当前状态 `Exited (255)`。
  **开工先 `docker start langgraph-postgres` 确认能起来**；数据落在匿名卷上，
  建议补一个具名卷（像 Milvus 那样），否则容器重建即丢 checkpoint。
  连接串形如 `postgresql://langgraph_user:<password>@127.0.0.1:5432/langgraph_db`。
- **产出**：`langgraph-checkpoint-postgres` + `psycopg`、`agent/graph.py` 接 `AsyncPostgresSaver`、
  `thread_id = conversations.conv_no`。
- **判据**：提交申请后图停在"等待审批"（此刻 MySQL 为 pending、流水 0 条）；管理员批准后图能 resume 推进；
  E06 等待审批时重启 → 恢复同一申请而不是重新创建。
- **坑**：checkpointer 自己建表，**不进 Alembic、不建 ORM 模型**；它走自己的连接池，
  与业务事务不共享，别指望它和 MySQL 组成一个原子事务。

### Day 13｜9/27（周日）跨库一致性 + E 类（缓冲日）

- **产出**：`services/recovery.py`、`tests/test_recovery.py`。
- **判据**：E07/E09/E10/E11/E12 通过 ——
  MySQL 提交成功但 checkpoint 保存失败 → 恢复时查既有结果、**不重复退款**；
  旧 checkpoint 停在待审批但 MySQL 已 refunded → **以 MySQL 为准，不执行**；
  PostgreSQL 不可用 → 明确报恢复失败，**不静默新建上下文执行写入**。
- **坑**：一句话记住 —— **MySQL 是权威，checkpoint 是缓存**。稳定业务操作 ID 先在 MySQL 幂等提交，
  再更新图状态。这句话要写进 README。

---

## 第五段｜第⑦⑧步 交付与评测（Day14–Day15）

### Day 14｜9/28（周一）前端最小闭环 + Docker Compose（可牺牲）

- **产出**：`web/`（React + TS + Vite）、SSE 流式对话、管理员审批页、`docker-compose.yml`。
- **判据**：浏览器里走完"提问 → 查订单 → 提申请 → 管理员批准 → 看到退款成功"；
  F03 SSE 断开重连用事件 ID 或状态查询恢复，**不重做业务操作**。
- **说明**：这一步对面试价值最低（比"能点"更稀缺的是"有数字"）。若前面拖期，**优先砍它**。

### Day 15｜9/29（周二）评测报告 + 项目收口

- **产出**：`docs/eval-report.md`、README 补"不做什么及为什么"、LangSmith 数据集与实验。
- **判据**：所有指标都能追到具体 run；
  A 类 Accuracy ≥90% / Macro-F1 ≥0.88；C 类 Recall@5 ≥85%、回答级幻觉率 ≤5%；
  端到端成功率 ≥85%；附 P50/P95、token 与成本、失败分类、样本数与**分子分母**；
  F07（全拒答导致低幻觉率）必须同时报覆盖率与成功率，不能宣称整体达标。
- **坑**：报告必须写清数据集版本、模型、样本数、失败样例 ——
  "同一份数据集上三档对比的数字 + 分子/分母 + 失败分类"才是这个项目真正的亮点，架构选型不是。

---

## 待拍板 / 已拍板

| # | 决策 | 状态与结论 | 最晚 |
| --- | --- | --- | --- |
| 1 | 移除 `deepagents` | ✅ **已执行**（9/15）。entry point 用户要求**暂不动**，实测正常、无需修 | 已完 |
| 2 | 消息历史与图状态存哪 | ✅ **已定**：正文与 checkpoint 进 PostgreSQL，MySQL 只留会话 id + 归属 | 已定 |
| 3 | 会话槽位放哪 | ❓ 待拍板：MySQL 一张表，或跟图 state 走。若按"MySQL 只记 id"，倾向图 state，代价见 Day9 | Day9 前 |
| 4 | embedding 模型 | ✅ **已定且已通**：`text-embedding-v4`，1024 维，单行 ≤8192 token、单次 ≤10 条 | 已定 |
| 5 | reranker 选型 | ✅ **已定且已通**：`gte-rerank-v2`（百炼），走原生接口，通用域名可直接调，复用 `DASHSCOPE_API_KEY` | 已定 |
| 6 | PostgreSQL 用 Docker 还是本机 | ✅ **已定**：Docker，容器 `langgraph-postgres`（postgres:16）已存在，待确认能启动 | 已定 |

---

## 弹性规则

1. **Day7、Day13 是缓冲**：前面拖期由它们吸收。
2. **压缩顺序（从先砍到后砍）**：前端（Day14）→ 中文分词细节验证 → Docker Compose。
   **不能压的是**：B/E 类的并发与幂等断言、评测报告（Day15）。
3. **每天一个 commit**，message 写清"为什么"而不是"改了什么"。
   第③步结束后 `git tag m3-refund-closed`，方便面试时回看演进。
4. 每天开工先 `docker compose up -d`（Milvus 未配开机自启），否则 Day10 之后的故事全断。
