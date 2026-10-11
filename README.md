# SupportFlow

**基于 LangGraph、混合检索与人工审批的智能售后助手。**

SupportFlow 将订单查询、产品使用咨询、售后政策问答和退款办理整合到同一个对话入口。客户描述问题后，系统识别需求：订单与退款由 Agent 调用业务工具处理，产品与政策问题先查询知识库，资料不足时通过 Tavily 搜索网上公开信息，再由模型组织回答。

前端采用 Vue 3，后端采用 FastAPI。对话通过 SSE 流式输出；刷新页面后，前端自动恢复当前会话，并从后台读取正在生成的文字及最终结果。退款申请需要管理员审批，审批完成后恢复关联的对话。

支持新建、切换和删除会话，首次对话后自动生成标题；配置 PostgreSQL 可持久化对话历史。

> 项目使用演示订单与模拟退款，不接入真实支付。签收后 14 天的退款期限是项目演示规则；知识库条款和网上信息用于咨询，实际退款资格由业务代码与订单数据判定。

## 功能

| 使用方 | 能力 |
| --- | --- |
| 客户 | 查询本人订单、商品明细、退款资格、退款申请与审批结果 |
| 客户 | 咨询产品使用及售后政策，查看本地资料或网页来源 |
| 客户 | 在对话或订单页面提交退款申请，新建、切换和删除会话 |
| 客户 | 接收流式回复，刷新后恢复原会话和生成中的文字 |
| 管理员 | 查看订单、退款申请、审批记录及模拟退款流水，批准或拒绝申请 |
| 服务端 | 校验身份与订单归属，执行退款规则，保存对话状态，恢复人工审批中断 |

![SupportFlow 客户售后工作台](pic/img.png)

## 对话执行流程

总图使用一个统一售后 Agent。`understand_and_route` 识别本轮需求，决定是否先检索资料；内部 Agent 根据历史与本轮证据选择订单、退款工具或直接回答。

```mermaid
flowchart TD
    START([客户发送消息]) --> ROUTE[understand_and_route<br/>识别需求并整理检索问题]
    ROUTE -->|订单、退款或其他需求| AGENT[support_agent<br/>统一售后 Agent]
    ROUTE -->|产品使用或政策问题| RETRIEVE[retrieve_knowledge<br/>本地混合检索]
    RETRIEVE -->|ready：有候选资料| AGENT
    RETRIEVE -->|empty / unavailable| WEB[search_web<br/>Tavily 联网搜索]
    WEB -->|网页资料或明确的失败状态| AGENT
    AGENT -->|需要业务事实或办理退款| TOOLS[订单与退款工具<br/>权限、资格和事务校验]
    TOOLS --> AGENT
    AGENT -->|没有待审批申请| END([本轮结束])
    AGENT -->|已提交待审批申请| WAIT[wait_for_approval<br/>暂停图并等待管理员]
    WAIT --> DECISION[管理员批准或拒绝<br/>先提交 MySQL 业务结果]
    DECISION --> RESUME[恢复同一会话<br/>读取审批结果并追加答复]
    RESUME --> END
```

- 会话 ID 由服务端生成 UUID，始终与 LangGraph 的 `thread_id` 一致。
- 客户端只提交本轮新消息，历史由 checkpointer 恢复。
- 每轮清空旧检索来源，避免换商品或换问题后沿用上轮证据。
- 总图保存对话状态；内部 Agent 使用传入历史，不另建一份长期记忆。
- 用户身份与数据库连接通过运行上下文和工具闭包传入，模型不能自行填写用户 ID。

实现入口：[图结构](src/supportflow/agents/graph/builder.py)、[节点逻辑](src/supportflow/agents/graph/nodes.py)、[统一 Agent](src/supportflow/agents/agent/support_agent.py)。

## 知识检索与联网兜底

### 本地混合检索

产品与政策问题进入 `retrieve_knowledge`，并行执行两路召回：

```mermaid
flowchart LR
    QUERY[本轮问题与商品型号] --> VECTOR[向量召回<br/>百炼 Embedding + Milvus]
    QUERY --> BM25[关键词召回<br/>本地资料 + jieba + BM25]
    VECTOR --> RRF[RRF 排名融合与去重]
    BM25 --> RRF
    RRF --> RERANK[Reranker 重排<br/>可配置关闭]
    RERANK --> DOCS[本轮候选资料与来源]
```

单路召回失败但另一路有结果时，仍然使用可用候选。重排失败时退回 RRF 融合顺序。有服务故障且没有候选时，状态为 `unavailable`；两路正常但都没有匹配时，状态为 `empty`。

知识库从 `src/supportflow/retrieval/data/` 与 `src/supportflow/retrieval/policies/` 递归读取 Markdown、PDF、DOCX，按标题和条款切分，保留文档、片段、来源和章节等元信息。BM25 完整统计保存为本地 JSON 快照，后端启动时加载到内存，同时预热 jieba 词典；向量索引保存在 Milvus。

### 联网兜底

本地状态为 `empty` 或 `unavailable` 时，总图自动进入 `search_web`。配置 `TAVILY_API_KEY` 后，节点发起真实搜索，将网页标题、URL 和摘要交给模型，再进入 `support_agent`。

**当前搜索由图节点执行。** 内部 Agent 绑定的是订单与退款工具，搜索节点负责获取网页资料；仅在提示词里写“上网搜索”不会代替这次外部调用。

| 情况 | 实际行为与回答依据 |
| --- | --- |
| 本地检索 `ready` | 使用本轮本地候选资料，不执行联网兜底 |
| 本地无结果或不可用，联网 `ready` | 说明本地未检索成功，基于网上公开信息回答并展示来源链接 |
| 联网 `empty` | 说明联网也未找到可用资料；一般性建议注明未经联网核实 |
| 联网 `unavailable` | 说明联网搜索不可用；不把模型已有知识标为网上检索结果 |
| 联网 `not_requested` | 本轮尚未执行或无需执行联网搜索 |

本地来源保存在 `retrieved_sources`，网页来源保存在 `web_sources`。这些是候选依据，不表示模型实际引用了每一条；检索分数也不代表答案正确率。证据正文作为本轮上下文提供给模型，不追加为聊天消息。

网上资料不能替代订单与退款工具的结果，也不能作为本店实际售后承诺。更换问题后，系统重新获取本轮证据。

实现入口：[混合检索](src/supportflow/retrieval/retrieving/hybrid.py)、[联网搜索客户端](src/supportflow/agents/tools/web_search.py)、[回答规则](src/supportflow/agents/prompt/system.py)。

## SSE 流式输出与刷新恢复

前端通过 `POST /customer/conversations/{id}/messages/stream` 发送新消息。服务端校验会话归属后，启动独立的后台图任务和 MySQL Session，再把助手文字转发到 SSE 连接。

| SSE 事件 | 数据与作用 |
| --- | --- |
| `delta` | `{ "text": "增量文字" }`，追加到当前助手草稿 |
| `done` | 完整本轮结果，包含用户消息、正式答复、审批状态和检索来源，替换草稿 |
| `error` | `{ "status": 502, "message": "错误提示" }`，前端读取历史核对执行状态 |

SSE 开始后，错误通过事件传递，HTTP 状态可能仍为 200。网络分块不等于事件边界，前端解析器会保留不完整事件，直到收到完整报文。

### 刷新后如何恢复

刷新页面只断开浏览器的 SSE 连接，已开始的后台任务继续执行、写入 checkpoint 并释放运行锁。恢复流程如下：

```mermaid
sequenceDiagram
    participant UI as 客户页面
    participant API as 会话接口
    participant WORKER as 后台图任务
    participant STORE as Checkpointer
    UI->>API: POST messages/stream
    API->>WORKER: 启动任务，使用独立数据库会话
    WORKER-->>UI: SSE delta
    Note over UI,WORKER: 页面刷新，SSE 断开，后台任务继续
    UI->>API: 恢复选中会话，GET messages
    API-->>UI: 历史 + running + active_turn
    loop running 为 true 时，每 2 秒
        UI->>API: GET messages
        API-->>UI: 最新生成文字与运行状态
    end
    WORKER->>STORE: 保存本轮状态与正式消息
    UI->>API: GET messages
    API-->>UI: running=false，正式答复或失败提示
```

前端按登录账号保存选中的会话 ID，重新加载后核对会话归属并恢复。历史接口返回：

| 字段 | 用途 |
| --- | --- |
| `items`、`total`、`offset`、`limit` | 正式消息与分页信息，前端读取最新 100 条 |
| `running` | 当前会话是否仍在执行，决定“正在回复”状态及发送锁定 |
| `active_turn` | 本轮用户消息与 `assistant_text` 文字快照；恢复时整体替换草稿并按消息 ID 去重 |
| `status`、`pending_request_key` | 已完成或等待审批，以及关联的退款申请编号 |
| `run_error` | 后台执行失败的提示，避免任务失败后页面一直等待 |
| `retrieval_status`、`retrieved_sources` | 最近一轮本地检索状态与候选来源 |
| `web_search_status`、`web_sources` | 最近一轮联网搜索状态与网页来源 |

前端以服务端运行状态判断任务是否结束，不能用“消息条数变多”判断完成。后台失败且没有新答复时，也会解除运行锁并展示错误。等待审批期间每 4 秒读取历史；SSE 报错或断流后立即核对历史，不自动重新提交消息。

实现入口：[会话服务](src/supportflow/services/conversations.py)、[会话 API](src/supportflow/api/customer/conversations.py)、[客户对话页面](web-vue/src/pages/customer/CustomerHomePage.vue)。

## 退款办理与人工审批

退款由后端业务服务校验与执行。演示规则为：订单已支付、已签收，签收后 **14 天内（含边界）** 可申请整单全额退款，金额取数据库中的实付金额，申请原因不能为空。已有占用名额的申请或已退款订单不允许重复办理。

1. 客户明确退款意愿、订单和原因；Agent 调用工具核对订单与退款资格。
2. `post_refund` 提交待审批申请，本轮答复包含申请编号。
3. 总图进入 `wait_for_approval` 并中断，前端显示等待审批，暂时禁止在该会话发送新消息。
4. 管理员批准或拒绝。批准时在同一个 MySQL 事务中写入审批、完成模拟退款、更新流水和订单状态。
5. 业务事务提交后，服务端恢复同一个 `thread_id`，重新读取审批结果并追加客户可见答复。
6. 前端轮询历史，显示结果并恢复输入框。

审批已提交但图恢复失败时，管理员可调用 `POST /admin/refund-requests/{request_key}/resume` 重试恢复；重复恢复不会重复退款。业务提交与 PostgreSQL checkpoint 不构成跨库原子事务，图执行失败不代表业务操作全部回滚。

通过订单页面提交的申请可以在详情页查看结果。只有通过对话提交并进入审批节点的申请，才会触发该会话的中断与恢复。

## 技术与数据存储

| 层次 | 技术与用途 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vue Router、Vite：客户与管理员工作台、SSE 与恢复轮询 |
| 后端 | Python 3.13+、FastAPI、Pydantic、Uvicorn：异步接口与参数校验 |
| Agent | LangGraph、LangChain、DeepSeek：需求识别、工具调用、对话记忆和人工中断 |
| 业务存储 | MySQL、SQLAlchemy、asyncmy、Alembic：认证、订单、退款、事务与迁移 |
| 对话存储 | PostgreSQL、LangGraph Checkpointer、psycopg：消息历史与图状态 |
| 本地检索 | Milvus、jieba、BM25、RRF：向量与关键词召回、排名融合 |
| 向量与重排 | 百炼 `text-embedding-v4`、`qwen3-rerank` |
| 联网搜索 | Tavily、httpx：获取网页标题、链接与摘要 |
| 文档与测试 | pypdf、python-docx、pytest、Node.js Test Runner |

**MySQL 保存业务事实，PostgreSQL 保存对话过程，Milvus 保存可重建的知识向量索引。** 当前运行锁、正在输出的文字、后台任务和执行错误保存在后端进程内存中。

## 快速开始

### 1. 准备环境与依赖

- Python **3.13+**、uv、Node.js **22.12+** 和 npm。
- MySQL **8.0+**，创建空业务库，例如 `agent_project`。
- DeepSeek API Key，用于对话模型。
- PostgreSQL 用于持久化对话；Milvus Standalone 与百炼 API Key 用于向量检索、入库和重排。
- Tavily API Key，用于知识库检索失败后的联网兜底。

数据库服务需自行准备，仓库尚未提供 Docker Compose 一键启动文件。Milvus 不可用时，BM25 有匹配资料仍可回答；未配置 Tavily 时，联网分支会如实返回不可用状态。

在项目根目录安装后端依赖：

```bash
uv sync --locked
```

复制配置，已有 `.env` 时保留原配置并补齐新增项：

```powershell
# Windows PowerShell，首次配置时执行
Copy-Item .env.example .env
```

```bash
# Linux / macOS，首次配置时执行
cp .env.example .env
```

### 2. 配置 .env

常用配置见 [.env.example](.env.example)。以下配置使用占位值，需替换为自己的密码与密钥：

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=agent_project

DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
# 可选：覆盖默认对话模型
DEEPSEEK_MODEL=deepseek-v4-flash

DASHSCOPE_API_KEY=your_dashscope_api_key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIM=1024
DASHSCOPE_NATIVE_BASE_URL=https://dashscope.aliyuncs.com/api/v1
RERANK_MODEL=qwen3-rerank
RETRIEVAL_RERANK=true

MILVUS_URI=http://127.0.0.1:19530
DB_NAME=supportflow
COLLECTION=supportflow_knowledge

TAVILY_API_KEY=your_tavily_api_key
TAVILY_BASE_URL=https://api.tavily.com
WEB_SEARCH_MAX_RESULTS=5
WEB_SEARCH_TIMEOUT_SECONDS=15

# .env.example 尚未包含该项；需要持久化对话时手动添加
LANGGRAPH_PG_DSN=postgresql://langgraph_user:your_pg_password@127.0.0.1:5432/langgraph_db
```

| 配置 | 行为 |
| --- | --- |
| `LANGGRAPH_PG_DSN` 留空 | 使用内存 checkpointer，后端重启后对话历史丢失 |
| `LANGGRAPH_PG_DSN` 已配置 | 使用 PostgreSQL；连接失败会导致后端启动失败 |
| `TAVILY_API_KEY` 留空 | 不发送联网请求，搜索状态为 `unavailable` |
| `WEB_SEARCH_MAX_RESULTS` | 默认最多返回 5 条网页资料 |
| `WEB_SEARCH_TIMEOUT_SECONDS` | 默认搜索请求超时为 15 秒 |
| `RETRIEVAL_RERANK=false` | 关闭重排，使用 RRF 融合顺序 |
| `BM25_INDEX_PATH` | BM25 快照路径，默认 `.local/indexes/bm25.json`；相对路径以项目根目录为基准 |

修改 `.env` 后重启后端才能加载新配置。`.env` 已被 Git 忽略，不要提交真实密钥。

### 3. 初始化业务数据

确认 MySQL 中已创建配置的空数据库，执行迁移与演示数据初始化：

```bash
uv run alembic upgrade head
uv run python -m supportflow.db.seed.seed_demo
```

首次创建 `admin`、`customer1`、`customer2` 时，终端会输出随机生成的登录密码，请保存。已有账号不会重置密码。演示基线包含两位客户各 20 笔订单、20 条退款申请、15 条审批记录和 10 条退款流水，覆盖期限内外及不同处理状态。

需要恢复演示基线时执行：

```bash
uv run python -m supportflow.db.seed.seed_demo --refresh
```

`--refresh` 重置预设演示订单的明细与退款链路，保留账号密码、登录会话和聊天会话。已有手工建表的数据库需先核对结构与迁移版本，再执行迁移。

### 4. 导入本地知识库

```bash
# 检查解析与切分，不调用模型或数据库
uv run python -m supportflow.retrieval.resource2chunks --dry-run

# 生成向量并写入 Milvus，更新同 ID 片段，保留其他记录
uv run python -m supportflow.retrieval.resource2chunks

# 离线构建 BM25 快照，不调用模型或数据库
uv run python -m supportflow.retrieval.retrieving.bm25 --build-index
```

需要完整重建向量索引时可添加 `--replace`。该模式会在资料解析和向量生成成功后清空配置集合，再分批写入新资料；批次之间没有跨批次事务，失败后需重新运行。扫描 PDF 需先完成 OCR。

BM25 快照包含片段正文和 BM25 对象的完整统计状态。启动时快照存在就直接加载，不存在则首次构建并保存；随后在当前进程中缓存复用。首次部署可先运行离线构建命令，将构建工作放在服务启动之前。可用 `--index-path <路径>` 指定输出位置，服务需配置相同的 `BM25_INDEX_PATH`。

修改资料或切分、分词规则后，先更新 Milvus，再离线重建 BM25 快照，最后重启后端加载新版本。快照不做自动过期检测或损坏恢复；读取失败会中止启动，重新运行离线构建命令即可覆盖快照。构建命令应在启动前执行；多个后端进程各自加载内存副本。

### 5. 启动后端

Windows PowerShell：

```powershell
uv run uvicorn supportflow.main:app --host 127.0.0.1 --port 8080 --workers 1 --loop asyncio:SelectorEventLoop
```

Linux / macOS：

```bash
uv run uvicorn supportflow.main:app --host 127.0.0.1 --port 8080 --workers 1
```

Windows 使用 PostgreSQL 异步驱动时采用 SelectorEventLoop。后端使用 **8080** 端口，与前端代理一致。当前会话运行保护依赖进程内状态，应以单 worker 运行。

- [健康检查](http://127.0.0.1:8080/health)：返回 `{"status":"ok","service":"supportflow"}`。
- [API 文档](http://127.0.0.1:8080/docs)：查看请求、响应与认证要求。

健康检查只反映 API 进程存活，不验证数据库、模型或检索服务。

### 6. 启动前端

另开终端：

```bash
cd web-vue
npm ci
npm run dev
```

访问 [客户与管理员工作台](http://127.0.0.1:4173)，使用初始化时生成的账号密码登录。Vite 将 `/api` 请求代理到后端 **8080**，转发前去掉 `/api` 前缀。

## 体验流程

1. 登录客户账号，查询最近订单，并查看具体订单的商品明细和退款资格。
2. 询问“米家洗衣机童锁怎么使用”，查看知识库回答与本地来源。
3. 询问本地没有资料的问题；如果本地确实返回 `empty` 或 `unavailable`，会进入 Tavily 搜索，回答中说明网上来源。本地有候选时不会调用联网兜底。
4. 在回复生成过程中刷新页面，确认自动回到原会话，显示生成中的文字并最终替换为正式答复。
5. 明确需要退款的订单与原因，提交申请后确认会话进入等待审批。
6. 登录管理员账号批准或拒绝申请，回到客户会话查看恢复后的答复，并在申请详情核对业务状态。

## 开发验证

后端离线回归，在项目根目录执行：

```bash
uv run pytest tests -q
```

前端测试、类型检查与生产构建，在 `web-vue/` 执行：

```bash
npm test
npm run typecheck
npm run build
```

后端测试覆盖认证、权限、退款规则、审批恢复、图路由、混合检索、联网搜索客户端，以及 SSE 断开后的后台执行与历史恢复。前端测试覆盖恢复草稿、分页、运行状态和 SSE 分块解析。`npm run build` 同时执行类型检查。

这些测试使用模拟模型、搜索响应和离线业务环境。真实联网搜索需要有效的 Tavily 配置；真实模型、MySQL、PostgreSQL 和 Milvus 的完整链路按体验流程联调。

## 项目结构

```text
supportflow/
├── src/supportflow/
│   ├── main.py                    # FastAPI 入口与生命周期
│   ├── api/                       # 登录、客户和管理员接口
│   ├── agents/
│   │   ├── graph/                 # 路由、知识检索、联网搜索、审批中断
│   │   ├── agent/                 # 统一售后 Agent
│   │   ├── tools/                 # 订单、退款工具和搜索客户端
│   │   └── prompt/                # 路由提示与回答规则
│   ├── services/                  # 业务规则、审批和后台对话执行
│   ├── repository/                # 数据访问
│   ├── models/                    # SQLAlchemy 实体
│   ├── schemas/                   # API 请求与响应
│   ├── core/                      # 配置、认证与安全
│   ├── db/                        # MySQL 会话与演示数据脚本
│   └── retrieval/
│       ├── data/                  # 产品说明书与常见问题
│       ├── policies/              # 政策资料
│       ├── retrieving/            # 向量、BM25、RRF 与重排
│       └── resource2chunks.py     # 多格式解析与入库
├── web-vue/
│   ├── src/                       # 页面、组件、API、认证与样式
│   └── tests/                     # 恢复逻辑与 SSE 测试
├── alembic/                       # 数据库迁移
├── tests/                         # 后端测试
├── pic/                           # 页面截图
├── .env.example                   # 配置模板
├── pyproject.toml
└── uv.lock
```

## 当前边界

- 刷新恢复针对浏览器断线：后台进程仍在运行时，任务可以继续完成。后端进程重启不会自动续跑执行中的任务；PostgreSQL 可以保留已保存的图状态与消息，但不会代替任务调度器。
- 当前没有跨进程运行锁或共享文字缓存，多 worker 需要额外的共享运行状态与并发保护。
- 本轮执行中或等待审批时，新消息返回 409；执行中的会话不能删除。重复发送是新的一轮，当前没有消息请求幂等键。
- 图或网络报错后不会自动重新执行消息，因为工具可能已经提交退款申请；应先核对历史、订单和申请状态。
- 网页检索和本地候选都需要模型判断适用性；无法取得资料时，回答如实说明局限，具体业务结果仍由后端工具确认。
