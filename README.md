# SupportFlow

用于学习和面试展示的智能售后工单 Agent。当前完成项目约定与最小 HTTP 服务，业务、Agent、检索和审批尚未实现。

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

执行只读连接检查：

```powershell
& "$env:USERPROFILE/.local/bin/uv.exe" --cache-dir .uv-cache run python -m supportflow.db.check
```

成功时输出数据库名和 `SELECT 1=1`，失败时退出码为 1。
连接模块位于 `src/supportflow/db/session.py`，提供连接池与 `get_db` 会话依赖；
业务层负责显式提交事务。当前不创建表，表结构和迁移留到下一步。

## 文件的作用

第一版业务表与状态说明见 [数据库结构](docs/database-schema.md)，实体位于 `src/supportflow/models/`。
当前已定义实体，尚未执行建表迁移。离线约束检查：`.venv/Scripts/python.exe -m unittest discover -s tests -v`。

- `pyproject.toml`：项目元信息和直接依赖，类似 Maven 的 pom.xml。
- `uv.lock`：精确依赖版本，协作和部署时复现环境。
- `src/supportflow/main.py`：FastAPI 应用和路由，类似 Web 后端的入口与 Controller。
- `src/supportflow/__init__.py`：`supportflow` 启动命令。
- [项目约定](docs/project-scope.md)：范围、技术栈、模拟规则及评测目标。
- [分层验收矩阵](docs/acceptance-cases.md)：后续实现的预期行为。

存储方案：MySQL 保存业务数据与会话归属，PostgreSQL 保存 LangGraph 状态，Milvus 保存政策索引。

下一步：MySQL、数据库迁移、模拟用户与订单、带归属检查的订单查询接口。

参考：[FastAPI 入门](https://fastapi.tiangolo.com/tutorial/first-steps/)、[uv 依赖管理](https://docs.astral.sh/uv/concepts/projects/dependencies/)。
