# SupportFlow

用于学习和面试展示的智能售后工单 Agent。当前已实现认证、角色依赖、订单种子及客户/管理员订单查询；退款、Agent、检索和审批仍待实现。最新检查与后续安排见 [开发计划](docs/plan-8-days.md)。

## 本地启动（Windows PowerShell）

在项目根目录执行。当前电脑的 uv 位于以下路径；无需修改全局 PATH：

```powershell
& "$env:USERPROFILE/.local/bin/uv.exe" --cache-dir .uv-cache sync --locked
& "$env:USERPROFILE/.local/bin/uv.exe" --cache-dir .uv-cache run supportflow
```

访问 http://127.0.0.1:8000/health，预期返回：

```json
{"status":"ok","service":"supportflow"}
```

接口文档：http://127.0.0.1:8000/docs 。Ctrl+C 停止服务。
开发时自动重载：

```powershell
& "$env:USERPROFILE/.local/bin/uv.exe" --cache-dir .uv-cache run uvicorn supportflow.main:app --reload
```

`/health` 只表示 API 进程正常，不表示数据库、模型或检索可用。

## MySQL 连接

在根目录 `.env` 中配置 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、
`MYSQL_PASSWORD`、`MYSQL_DATABASE`，字段示例见 `.env.example`。
本地默认地址为 `127.0.0.1:3306`，数据库为 `agent_project`。
真实密码只保存在被 Git 忽略的 `.env` 中。

2026-09-17 核对：旧文档提到的 `supportflow.db.check` 模块当前不存在；本轮只读连接检查因缺少 `cryptography`、无法完成 MySQL SHA-2 认证而失败，需先补齐依赖后复核。
连接模块位于 `src/supportflow/db/session.py`，使用 asyncmy 和 SQLAlchemy 异步连接池，
提供 `AsyncSession` 类型的 `get_db` 会话依赖；业务层使用 `await session.execute(...)`
和 `await session.commit()` 执行查询、显式提交事务。并发任务各用独立会话，
不在等待模型回复或人工审批期间保持数据库事务。

## 前端

项目中同时存在 `web/`（React）与 `web-vue/`（Vue）。Vue 版类型检查和生产构建已通过，开发服务器为 `http://127.0.0.1:5174`，当前代理目标为后端 8080 端口。联调 Vue 时在项目根目录运行：

```powershell
.venv/Scripts/python.exe -m uvicorn supportflow.main:app --host 127.0.0.1 --port 8080
```

另开终端执行 `cd web-vue`、`npm ci`（首次安装）、`npm run dev`。订单页面已接 API；退款申请和审批按钮尚未启用。仅构建通过不代表数据库和浏览器联调已完成。

## 文件的作用

第一版业务表与状态说明见 [数据库结构](docs/database-schema.md)，实体位于 `src/supportflow/models/`。
已配置 Alembic，初始版本包含七张业务表。新库建表、已有库接入和后续变更见 [数据库迁移说明](docs/database-migrations.md)。离线约束及迁移检查：`.venv/Scripts/python.exe -m unittest discover -s tests -v`。

- `pyproject.toml`：项目元信息和直接依赖，类似 Maven 的 pom.xml。
- `uv.lock`：精确依赖版本，协作和部署时复现环境。
- `src/supportflow/main.py`：FastAPI 应用和路由，类似 Web 后端的入口与 Controller。
- `src/supportflow/__init__.py`：`supportflow` 启动命令。
- [项目约定](docs/project-scope.md)：范围、技术栈、模拟规则及评测目标。
- [分层验收矩阵](docs/acceptance-cases.md)：后续实现的预期行为。

存储方案：MySQL 保存业务数据与会话归属，PostgreSQL 保存 LangGraph 状态，Milvus 保存政策索引。

下一步：恢复 MySQL 连接，补齐认证与订单隔离验收，再实现退款资格、申请与进度查询。订单种子入口为 `python -m supportflow.db.seed.seed_orders`，依赖先运行用户种子 `python -m supportflow.db.seed.seed_users`。

参考：[FastAPI 入门](https://fastapi.tiangolo.com/tutorial/first-steps/)、[uv 依赖管理](https://docs.astral.sh/uv/concepts/projects/dependencies/)。
