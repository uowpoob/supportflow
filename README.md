# SupportFlow

用于学习和面试展示的智能售后工单 Agent。当前已实现认证、角色依赖、订单查询，以及退款资格判定 / 申请 / 审批 / 模拟退款全链路；Agent 对话、政策检索与部署脚本仍待实现。最新检查与后续安排见 [开发计划](docs/plan-8-days.md)。

## 本地启动（Windows PowerShell）

在项目根目录执行。当前电脑的 uv 位于以下路径；无需修改全局 PATH：

```powershell
& "$env:USERPROFILE/.local/bin/uv.exe" --cache-dir .uv-cache sync --locked
& "$env:USERPROFILE/.local/bin/uv.exe" --cache-dir .uv-cache run uvicorn supportflow.main:app --host 127.0.0.1 --port 8080 --loop asyncio:SelectorEventLoop
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

## 前端

`web-vue/`（Vue 3）是当前使用的版本；`web/`（React 初版）已于 2026-09-18 从 git 索引移除 ——
只留在工作区，不再参与版本管理。Vue 版类型检查和生产构建均通过，开发服务器为
`http://127.0.0.1:5174`，代理目标为后端 8080。先启动后端，再另开终端执行
`cd web-vue`、`npm ci`（首次安装）、`npm run dev`。

页面与组件已按域分包：`pages/{auth,customer,admin}`、`components/{common,orders,refunds}`。
退款相关的写操作（提交申请 / 批准 / 拒绝）已接通并做过真机验收，其余未涉及的写操作仍是禁用状态。
仅构建通过不代表联调已完成 —— 浏览器端验收脚本见 `.workbuddy/tools/browser_acceptance.mjs`。

## 文件的作用

第一版业务表与状态说明见 [数据库结构](docs/database-schema.md)，实体位于 `src/supportflow/models/`。
已配置 Alembic，初始版本包含七张业务表。新库建表、已有库接入和后续变更见 [数据库迁移说明](docs/database-migrations.md)。自动化测试：`.venv/Scripts/python.exe -m unittest discover -s tests -v`，或 `uv run pytest -q`（当前 38 项通过、52 个子用例）。

- `pyproject.toml`：项目元信息和直接依赖，类似 Maven 的 pom.xml。
- `uv.lock`：精确依赖版本，协作和部署时复现环境。
- `src/supportflow/main.py`：FastAPI 应用和路由，类似 Web 后端的入口与 Controller。
- `src/supportflow/__init__.py`：`supportflow` 启动命令。
- [项目约定](docs/project-scope.md)：范围、技术栈、模拟规则及评测目标。
- [分层验收矩阵](docs/acceptance-cases.md)：后续实现的预期行为。

存储方案：MySQL 保存业务数据与会话归属，PostgreSQL 保存 LangGraph 状态，Milvus 保存政策索引。

演示数据入口：先跑 `python -m supportflow.db.seed.seed_users`，再跑 `seed_orders`
（`--refresh` 可把已存在订单的支付/签收时间重新锚定到当前时刻），退款占位数据用 `seed_refunds`。
把库还原到验收基线用 `.workbuddy/tools/reset_refund_state.py`。

下一步：接入模型与 LangGraph（订单/退款工具、多轮追问、PostgreSQL checkpoint），再做政策检索，最后补部署脚本与评测报告。

参考：[FastAPI 入门](https://fastapi.tiangolo.com/tutorial/first-steps/)、[uv 依赖管理](https://docs.astral.sh/uv/concepts/projects/dependencies/)。
