# SupportFlow

**基于 LangGraph 与 RAG 的智能售后助手**

SupportFlow 将订单查询、产品问题解答、售后政策咨询和退款办理整合到同一个对话入口。客户可以通过自然语言描述问题，助手结合订单工具和知识库提供回答；涉及退款时，由后端校验业务规则，再交给管理员审批，完成模拟退款与会话恢复。

项目采用 Vue 3 + FastAPI 前后端分离架构，使用 MySQL 保存业务数据、PostgreSQL 保存对话状态、Milvus 保存知识向量。适合用于学习 Agent 工具调用、混合检索、人工审批和业务系统集成。

> 本项目使用演示订单与模拟退款，不接入真实支付。演示退款规则为项目自定义规则，与知识库中的法律条款、品牌售后政策分别处理。

## 功能介绍

### 客户工作台

- **智能售后对话**：识别订单、退款、产品使用和政策咨询等需求，信息不足时追问，通过 SSE 流式展示回复。
- **订单查询**：查看本人订单、商品明细、支付与物流状态，以及退款资格。
- **产品与政策问答**：检索小米、REDMI、米家相关说明书、常见问题和售后政策，展示回答使用的资料来源。
- **退款申请与进度查询**：支持在对话中办理，也支持通过订单页面提交申请，查看申请状态和审批意见。
- **会话管理**：新建、切换和删除会话，首次对话后自动生成标题；配置 PostgreSQL 后可持久化对话历史。

### 管理员工作台

- 查看订单、退款申请、审批记录和模拟退款流水。
- 批准或拒绝退款申请，并填写审批意见。
- 批准时在同一个 MySQL 事务中完成审批与模拟退款，更新申请、流水和订单状态。
- 审批后恢复关联的 Agent 会话，向客户补充处理结果。

### Agent 与知识检索

- **统一售后 Agent**：订单与退款共用一个 Agent，结合消息历史选择工具；产品与政策问题先检索知识，再组织回答。
- **人工审批中断与恢复**：对话提交退款申请后，LangGraph 暂停在审批节点；管理员处理后，重新读取业务结果并恢复会话。
- **多格式知识入库**：递归读取 Markdown、PDF、DOCX，按标题和条款切分，保留来源、页码等元信息。
- **混合检索**：向量召回与本地 BM25 召回并行执行，经 RRF 融合后使用 Reranker 重排；重排不可用时退回融合结果。
- **业务校验与权限隔离**：订单和会话归属由服务端认证身份校验，退款金额取数据库实付金额；事务、行锁和唯一约束用于控制重复申请与重复退款。

演示退款仅支持已支付、已签收且签收后 **14 天内（含边界）** 的整单全额退款。申请必须填写原因，已退款订单不可重复退款。

## 项目结构

```text
supportflow/
├── src/supportflow/            # Python 后端
│   ├── main.py                # FastAPI 应用入口
│   ├── api/                   # 登录、客户与管理员接口
│   ├── agents/                # Agent、LangGraph 状态图、提示词与工具
│   ├── core/                  # 配置、认证与安全工具
│   ├── db/                    # 数据库连接与演示数据脚本
│   ├── models/                # SQLAlchemy 数据实体
│   ├── repository/            # 订单、退款与会话数据访问
│   ├── services/              # 业务规则、审批与对话执行
│   ├── schemas/               # API 请求与响应结构
│   └── retrieval/             # 知识解析、向量入库与检索
│       ├── data/              # 产品说明书与常见问题资料
│       ├── policies/          # 售后与消费者权益政策资料
│       ├── retrieving/        # 向量、BM25、RRF 与重排
│       └── resource2chunks.py # 多格式切分与入库入口
├── web-vue/                   # Vue 3 前端
│   └── src/
│       ├── pages/             # 登录、客户与管理员页面
│       ├── components/        # 对话、订单、退款与通用组件
│       ├── api/               # API 请求与 SSE 处理
│       ├── auth/              # 登录状态与路由权限
│       └── styles/            # 页面样式
├── alembic/                   # 数据库迁移
├── tests/                     # 业务、接口、Agent 与检索测试
├── pic/                       # 项目展示截图
├── .env.example               # 环境变量示例
├── pyproject.toml             # Python 项目配置与依赖
└── uv.lock                    # Python 依赖锁定文件
```

## 主要技术

| 层次 | 技术 | 用途 |
| --- | --- | --- |
| 前端 | Vue 3、TypeScript、Vue Router、Vite | 客户与管理员工作台、路由与页面构建 |
| 后端 | Python 3.13、FastAPI、Pydantic、Uvicorn | 异步 API、参数校验与服务运行 |
| Agent | LangGraph、LangChain、DeepSeek | 意图识别、工具调用、多轮对话与审批恢复 |
| 业务存储 | MySQL、SQLAlchemy、asyncmy、Alembic | 业务数据、异步访问、事务与迁移 |
| 对话存储 | PostgreSQL、LangGraph Checkpointer、psycopg | 消息历史与图状态持久化 |
| 知识检索 | Milvus、jieba、BM25、RRF | 语义与关键词双路召回、排名融合 |
| 向量与重排 | 百炼 `text-embedding-v4`、`gte-rerank-v2` | 文本向量化与候选重排 |
| 文档解析 | pypdf、python-docx | PDF、Word 文本与表格提取 |
| 流式交互与测试 | SSE、pytest、httpx、uv | 流式回复、自动化验证与依赖管理 |

三种存储分别负责不同的数据：**MySQL 是业务事实的来源，PostgreSQL 保存对话过程，Milvus 是可以从知识资料重建的检索索引**。BM25 索引在后端进程中按需构建。

对话的主要执行路径如下：

```mermaid
flowchart TD
    A[客户发送消息] --> B[识别需求]
    B -->|订单与退款| C[统一售后 Agent]
    B -->|产品与政策| D[向量 + BM25 召回]
    D --> E[RRF 融合 + Reranker 重排]
    E --> C
    C --> F[订单与退款工具]
    F --> G[后端权限和业务校验]
    G --> C
    C -->|普通回复| H[返回结果与资料来源]
    C -->|已提交待审批申请| I[暂停会话，等待人工审批]
    I --> J[管理员批准或拒绝]
    J --> K[读取业务结果并恢复会话]
    K --> H
```

## 项目展示

### 客户售后工作台

左侧提供订单与退款申请入口，中间显示历史会话，右侧为智能售后对话区。客户可以从查询订单、了解售后政策或申请退款开始，也可以直接描述产品问题。

![SupportFlow 客户售后工作台](pic/img.png)

### 演示数据与体验流程

演示商品覆盖小米、REDMI、米家的手机、电脑、平板、音频、配件、穿戴、网络设备和家电，金额为模拟成交价。

| 数据 | 内容 |
| --- | --- |
| 账号 | 两个客户 `customer1`、`customer2`，一个管理员 `admin` |
| 订单 | 每位客户 20 单，共 40 单，包含不同支付、物流状态及退款期限内外的场景 |
| 退款申请 | 20 条，待审批、已批准、已拒绝、已退款各 5 条 |
| 审批与流水 | 15 条审批记录、10 条退款流水，流水包含打款中与成功状态 |

建议从以下流程体验项目：

1. 登录客户账号，在“我的订单”中查看订单和退款资格。
2. 向助手发送“帮我查询最近的订单”，再选择符合条件的订单并说明退款原因。
3. 提交申请后，登录管理员账号，在退款申请详情中批准或拒绝。
4. 返回客户会话查看审批结果，并在申请详情中核对业务状态。
5. 询问“米家洗衣机童锁怎么使用”或“手机耗电快怎么办”，查看知识回答及资料来源。

页面提交的退款申请可从申请详情查看结果；只有通过对话提交并进入审批节点的申请才会触发该会话的中断与恢复。

## 快速开始

### 1. 准备环境

- Python **3.13+**、uv、Node.js **22.12+** 与 npm。
- MySQL **8.0+**，创建空业务库，例如 `agent_project`。
- DeepSeek API Key，用于智能对话。
- 完整体验还需 PostgreSQL、Milvus Standalone 和百炼 API Key，用于对话持久化、向量召回与重排。

本仓库暂未提供 Docker Compose 一键启动文件，数据库服务需自行准备。未配置 PostgreSQL 连接串时，对话状态使用内存存储，服务重启后丢失；配置了连接串但连接失败时，后端启动会失败。向量服务不可用时，如本地 BM25 能召回资料，检索会降级使用该路结果。

在项目根目录安装后端依赖并复制配置：

```bash
uv sync --locked
```

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

```bash
# Linux / macOS
cp .env.example .env
```

编辑 `.env`，填写业务库和模型配置。以下仅为示例，密码与密钥替换为自己的值：

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=agent_project

DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
# 可选：覆盖代码中的默认模型
DEEPSEEK_MODEL=deepseek-v4-flash

DASHSCOPE_API_KEY=your_dashscope_api_key
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIM=1024
RERANK_MODEL=gte-rerank-v2
RETRIEVAL_RERANK=true

# .env.example 未包含此项，需要手动添加；留空时使用内存记忆
LANGGRAPH_PG_DSN=postgresql://langgraph_user:your_pg_password@127.0.0.1:5432/langgraph_db

MILVUS_URI=http://127.0.0.1:19530
DB_NAME=supportflow
COLLECTION=supportflow_knowledge
```

其余配置可保留 `.env.example` 的默认值。`.env` 已被 Git 忽略，不要提交真实密钥。

### 2. 初始化业务数据

确认 MySQL 中已创建配置的空数据库，再执行表结构迁移和演示数据初始化：

```bash
uv run alembic upgrade head
uv run python -m supportflow.db.seed.seed_demo
```

首次创建账号时，终端会输出 `admin`、`customer1`、`customer2` 各自随机生成的密码，请保存用于登录。已有账号不会重置密码。

如需恢复演示订单和退款基线，可以单独运行：

```bash
uv run python -m supportflow.db.seed.seed_demo --refresh
```

`--refresh` 会重置预设演示订单的商品明细与退款链路，保留账号密码、登录会话和聊天会话。演示日期以执行时刻为基准。

已有手工建表的数据库需先核对结构并正确登记迁移版本，不要直接按空库流程执行初始建表迁移。

### 3. 导入知识库

资料位于 `src/supportflow/retrieval/data/` 和 `src/supportflow/retrieval/policies/`，支持 Markdown、PDF、DOCX。

```bash
# 先检查解析和切分，不调用模型或数据库
uv run python -m supportflow.retrieval.resource2chunks --dry-run

# 生成向量并写入配置的 Milvus 集合，更新同 ID 片段，保留其他记录
uv run python -m supportflow.retrieval.resource2chunks
```

如需完全重建知识库，可使用 `--replace`：它会在解析和向量生成成功后删除配置集合的全部旧记录，再写入新资料。分批写入没有跨批次事务，失败后需重新运行。扫描 PDF 需先完成 OCR；更新资料后重启后端，使 BM25 内存索引同步更新。

### 4. 启动后端

Windows PowerShell：

```powershell
uv run uvicorn supportflow.main:app --host 127.0.0.1 --port 8080 --loop asyncio:SelectorEventLoop
```

Linux / macOS：

```bash
uv run uvicorn supportflow.main:app --host 127.0.0.1 --port 8080
```

Windows 下使用 PostgreSQL 异步驱动时需要 SelectorEventLoop。后端端口使用 **8080**，与前端代理配置一致。

- 健康检查：<http://127.0.0.1:8080/health>
- API 文档：<http://127.0.0.1:8080/docs>

健康检查预期返回 `{"status":"ok","service":"supportflow"}`，仅表示 API 进程正常，不代表数据库、模型或检索链路均可用。

### 5. 启动前端

另开终端执行：

```bash
cd web-vue
npm ci
npm run dev
```

访问 <http://127.0.0.1:4173>，使用初始化时生成的账号密码登录。开发服务器将 `/api` 请求代理到后端 `8080` 端口。

### 6. 开发检查

在项目根目录运行后端测试：

```bash
uv run pytest -q
```

在 `web-vue/` 中检查前端类型与生产构建：

```bash
npm run build
```

测试覆盖登录、权限隔离、订单与退款规则、会话流式输出、Agent 路由、数据库迁移和知识检索等模块。离线测试使用模拟模型与业务环境，真实模型和数据库的端到端行为仍需按演示流程验证。
