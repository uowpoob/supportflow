# SupportFlow

用于学习和面试展示的智能售后工单 Agent。

**已实现**：登录认证与会话、角色依赖、订单查询、退款资格判定 / 申请 / 审批 / 模拟退款全链路、
Agent 对话（LangGraph 单图 + PostgreSQL checkpoint，支持人工审批中断与恢复、SSE 流式输出）、
政策知识检索（向量 / BM25 / RRF 融合 / 重排四段，附四档对比评测报告）。

**尚未实现**：一键启动的 compose、面向服务器的部署脚本与 nginx、LangSmith 评测报告。
分阶段记录见 [开发计划](docs/plan-8-days.md)。

## 本地启动

在项目根目录执行。先把 `.env.example` 复制成 `.env`，填三处密钥：

- `DEEPSEEK_API_KEY` —— **必填**，不填服务起不来
- `MYSQL_PASSWORD` —— 业务库密码，按本机 MySQL 实际情况填
- `DASHSCOPE_API_KEY` —— 向量化与重排用，不填则政策检索不可用（其余功能正常）

其余项 `.env.example` 里都已给了可直接使用的默认值；LangSmith 那几项是可选观测，默认关闭，不用管。

Windows PowerShell（当前电脑的 uv 在以下路径；无需修改全局 PATH）：

```powershell
& "$env:USERPROFILE/.local/bin/uv.exe" --cache-dir .uv-cache sync --locked
& "$env:USERPROFILE/.local/bin/uv.exe" --cache-dir .uv-cache run uvicorn supportflow.main:app --host 127.0.0.1 --port 8080 --loop asyncio:SelectorEventLoop
```

Linux / macOS 上去掉 `--loop asyncio:SelectorEventLoop` —— 那是 Windows 独有的坑（见下）：

```bash
uv sync --locked
uv run uvicorn supportflow.main:app --host 127.0.0.1 --port 8080
```

端口用 **8080**：`python -m supportflow` 内置的 8000 在本机绑不上（WinError 10013，
8000 落在 Windows `winnat` 的保留段里，不是有残留进程占着），前端 vite 的代理目标也是 8080。

`--loop asyncio:SelectorEventLoop` 不能省：Agent 的对话记忆存在 PostgreSQL，
连它的驱动 psycopg 跑不了 Windows 默认的 ProactorEventLoop。uvicorn 自己创建事件循环，
所以在启动脚本里设 `set_event_loop_policy` 是没用的，只能从命令行或 `uvicorn.run(...)` 传。
（`--reload` 也能跑通，但那是它在 reload 模式下换循环的副作用，生产不开 reload，别指望它。）

访问 http://127.0.0.1:8080/health，预期返回：

```json
{"status":"ok","service":"supportflow"}
```

接口文档：http://127.0.0.1:8080/docs 。Ctrl+C 停止服务。

`/health` 只表示 API 进程正常，不表示数据库、模型或检索可用。

## MySQL 连接

在根目录 `.env` 中配置 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、
`MYSQL_PASSWORD`、`MYSQL_DATABASE`，字段示例见 `.env.example`。
本地默认地址为 `127.0.0.1:3306`，数据库为 `agent_project`。
真实密码只保存在被 Git 忽略的 `.env` 中。

2026-09-18 核对：`cryptography` 已列入项目依赖 —— MySQL 8 默认的 `caching_sha2_password`
认证需要它，缺了会是 `/health` 返回 200 而 `/login` 直接 500（堆栈里出现 `sha2_rsa_encrypt`）。
连接检查已通过。
连接模块位于 `src/supportflow/db/session.py`，使用 asyncmy 和 SQLAlchemy 异步连接池，
提供 `AsyncSession` 类型的 `get_db` 会话依赖；业务层使用 `await session.execute(...)`
和 `await session.commit()` 执行查询、显式提交事务。并发任务各用独立会话，
不在等待模型回复或人工审批期间保持数据库事务。

## PostgreSQL 与 Milvus

这两个都是**可选**的：不启动照样能起服务，只是对应能力降级。

| 服务 | 存什么 | 不启动会怎样 |
| --- | --- | --- |
| PostgreSQL | LangGraph 对话记忆（checkpoint） | 退化成进程内存记忆，重启服务后历史消失 |
| Milvus | 政策语料索引（428 条向量） | 政策检索不可用，Agent 只能答订单 / 退款 |

PostgreSQL 起一个官方镜像容器即可（本项目开发时用的是 `postgres:16`）：

```powershell
docker run -d --name langgraph-postgres -p 5432:5432 `
  -e POSTGRES_DB=langgraph_db `
  -e POSTGRES_USER=langgraph_user `
  -e POSTGRES_PASSWORD=<自己定一个密码> `
  -v supportflow-pgdata:/var/lib/postgresql/data `
  postgres:16
```

⚠️ 一定要带 `-v ...:/var/lib/postgresql/data`：不加则数据落在匿名卷上，容器一删对话历史就没了。

然后在 `.env` 里把连接串指过去（**这一项原先没写进 `.env.example`，不配会静默退化成内存记忆**）：

```
LANGGRAPH_PG_DSN=postgresql://langgraph_user:<上面的密码>@127.0.0.1:5432/langgraph_db
```

Milvus 官方需要连带 MinIO 和 etcd 一共三个容器，装法见
[Milvus 官方文档](https://milvus.io/docs/install_standalone-docker.md)。
`.env` 里配 `MILVUS_URI`（默认 `http://127.0.0.1:19530`）、`DB_NAME`、`COLLECTION`。
知识资料放在 `src/supportflow/retrieval/policies/`（政策）和 `data/`（产品知识），
递归读取 Markdown、PDF、DOCX，按标题层级和法律条款切分；DOCX 同时提取表格，
PDF 保留来源页码。Markdown 支持 YAML 元信息。默认片段上限 1200 字符（含标题），
长正文按句末继续切分并保留 120 字符重叠，可通过 `--chunk-size`、`--chunk-overlap` 调整。

```powershell
# 只解析和切分，不调用模型或数据库
python -m supportflow.retrieval.resource2chunks --dry-run
# 清空旧知识数据，重新导入 policies 和 data 全部资料
python -m supportflow.retrieval.resource2chunks --replace
# 更新同 ID 的片段，保留其他已有记录
python -m supportflow.retrieval.resource2chunks
# 只删除知识集合全部记录，保留集合结构和索引
python -m supportflow.retrieval.resource2chunks --clear-only
```

`--replace` 先完成本地解析、全部向量生成和校验，再删除配置的
`DB_NAME.COLLECTION` 中全部旧记录。分批写入后核对本次 ID 和集合总数，
保留 `RetrievedChunk` 字段结构；写入不具备跨批次事务，写入失败后需重新运行。
同名不同格式文件分别入库，文档 ID 包含目录、相对路径和扩展名，避免相互覆盖。
扫描 PDF 没有文本层时须先 OCR；部分页面无文本时会提示对应页码。
后端若已建立 BM25 内存索引，更新资料后需重启后端，或在该进程调用
`clear_index_cache()`，使混合检索同步使用新资料。

## 前端

`web-vue/`（Vue 3）是当前使用的版本；`web/`（React 初版）已于 2026-09-18 从 git 索引移除 ——
只留在工作区，不再参与版本管理。Vue 版类型检查和生产构建均通过，开发服务器为
`http://127.0.0.1:4173`，代理目标为后端 8080。先启动后端，再另开终端执行
`cd web-vue`、`npm ci`（首次安装）、`npm run dev`。

页面与组件已按域分包：`pages/{auth,customer,admin}`、`components/{common,orders,refunds}`。
客户对话区（发消息、SSE 流式回复、进出会话恢复"等待审批"状态）与退款写操作
（提交申请 / 批准 / 拒绝）均已接通并做过真机验收，其余未涉及的写操作仍是禁用状态。
仅构建通过不代表联调已完成 —— 浏览器端验收脚本见 `.workbuddy/tools/browser_acceptance.mjs`。

## 文件的作用

第一版业务表与状态说明见 [数据库结构](docs/database-schema.md)，实体位于 `src/supportflow/models/`。
已配置 Alembic，初始版本包含七张业务表。新库建表、已有库接入和后续变更见 [数据库迁移说明](docs/database-migrations.md)。自动化测试：`uv run pytest -q`，或 `.venv/Scripts/python.exe -m unittest discover -s tests -v`（2026-09-24 实测：**175 项通过、52 个子用例**）。

- `pyproject.toml`：项目元信息和直接依赖，类似 Maven 的 pom.xml。
- `uv.lock`：精确依赖版本，协作和部署时复现环境。
- `src/supportflow/main.py`：FastAPI 应用和路由，类似 Web 后端的入口与 Controller。
- `src/supportflow/__init__.py`：`supportflow` 启动命令。
- [项目约定](docs/project-scope.md)：范围、技术栈、模拟规则及评测目标。
- [分层验收矩阵](docs/acceptance-cases.md)：后续实现的预期行为。

存储方案：MySQL 保存业务数据与会话归属，PostgreSQL 保存 LangGraph 状态，Milvus 保存政策索引。

演示数据入口：`python -m supportflow.db.seed.seed_demo`。已有数据改成新的演示基线时运行
`python -m supportflow.db.seed.seed_demo --refresh`，在一个事务内同步恢复订单、商品明细、
退款申请、审批和流水，时间统一锚定到本次执行时刻。只刷新声明的演示订单；已有账号密码、
登录会话和普通聊天保留。单独的 `seed_users` / `seed_orders` / `seed_refunds` 入口仍可使用。

商品统一为小米、REDMI、米家，涵盖手机、电脑、平板、音频、配件、穿戴、网络设备和家电；
金额均为模拟成交价。客户只有 `customer1`、`customer2`，每人 20 单；另保留 `admin` 供审批。
40 单覆盖未支付、待发货、运输中、已签收、14 天期限内/外、多商品、多件数量和整单退款。
20 条退款申请包含待审批、已批准、已拒绝、已退款各 5 条；配套 15 条审批和 10 条流水
（打款中、成功各 5 条），没有打款失败或重试数据。成功时订单、申请和流水状态同步。
核对真实数据库可运行 `.venv/Scripts/python.exe .workbuddy/tools/verify_demo_dataset.py`。

下一步：补一键启动的 compose（把 MySQL / PostgreSQL / Milvus 一次装好，免去手装三个数据库）、面向服务器的部署脚本，以及 LangSmith 评测报告。

参考：[FastAPI 入门](https://fastapi.tiangolo.com/tutorial/first-steps/)、[uv 依赖管理](https://docs.astral.sh/uv/concepts/projects/dependencies/)。
