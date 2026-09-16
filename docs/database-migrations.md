# 数据库迁移与种子数据

迁移记录表结构的变化；种子脚本写入演示数据，两者独立运行。

## 配置与文件

- `alembic.ini`：迁移目录和日志配置，不保存密码。
- `alembic/env.py`：读取 `MYSQL_*` 配置，通过 asyncmy 连接数据库，加载 ORM 元数据。
- `alembic/versions/0001_initial.py`：七张业务表的固定结构快照，不会随着 ORM 修改而改变。
- `alembic/versions/0002_auth_sessions_add_auth_sessions.py`：新增认证会话表；已有初始版本的数据库通过 `upgrade head` 升级。
- `alembic_version`：数据库中记录已执行版本的表，由 Alembic 管理。

连接信息优先使用系统环境变量，其次是项目根目录 `.env`。迁移只需要数据库配置，不需要模型 API 密钥。以下命令均在项目根目录执行。

## 新数据库

先创建空数据库并配置 `MYSQL_*`（迁移创建表，不创建数据库或数据库账号）：

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic current
```

在容器中使用同样的项目文件，通过环境变量传入数据库配置，运行 `python -m alembic upgrade head`。镜像必须包含 `alembic.ini`、`alembic/` 和项目代码；由单独的部署步骤执行迁移，避免多个应用副本同时迁移。

## 已经手工建表的数据库

不能直接运行初始建表迁移，否则会提示表已存在。先核对七张表的字段、类型、索引、外键、CHECK 约束和生成列，确认与 `0001_initial` 一致，再执行一次：

```powershell
.venv/Scripts/python.exe -m alembic stamp 0001_initial
.venv/Scripts/python.exe -m alembic current
.venv/Scripts/python.exe -m alembic check
```

`stamp` 只登记版本，不建业务表、不修复结构差异。不要对空库或未核对的数据库执行；不要使用 `stamp head` 跳过未来的真实迁移。

本项目接入时已核对本地七张业务表，自动结构比对无差异，并另外核对了 CHECK 与生成列。Alembic 对 MySQL 的 `active_order_id` 可能提示 computed default 无法修改：MySQL 反射带有字符集标记和额外括号，此列已人工核对表达式和 STORED 属性一致。该提示不能作为将来忽略生成列变化的理由。

## 以后修改结构

1. 修改 ORM 实体。
2. 生成新迁移：

   ```powershell
   .venv/Scripts/python.exe -m alembic revision --autogenerate -m "add auth sessions"
   ```

3. 阅读生成的 `upgrade()` 和 `downgrade()`，确认没有意外删表、删列。自动生成不能可靠识别重命名，也不能完整检测 CHECK、生成列等变更，必要时手写操作。
4. 在测试数据库验证后执行：

   ```powershell
   .venv/Scripts/python.exe -m alembic upgrade head
   .venv/Scripts/python.exe -m alembic check
   ```

已执行并共享的迁移不要修改；继续新增版本。MySQL DDL 并不保证事务回滚，上线前备份并审阅迁移。初始版本的 downgrade 会删除七张业务表，只能在可丢弃的测试库验证，不能用于保留数据的回退。

## 种子数据

迁移不自动插入演示账号。需要新建演示账号时单独执行：

```powershell
.venv/Scripts/python.exe -m supportflow.db.seed_users
```

现有脚本创建 admin、customer1、customer2，已存在的账号跳过，不重置密码；新账号密码随机生成并在首次创建时显示。妥善保存输出，不提交真实密码。

订单等测试数据建议按固定场景准备，例如“已支付未发货”“已签收超过 14 天”“其他客户的订单”，便于重复验收；大量随机数据可在以后用于性能测试。本次不生成新演示数据。

## 验证

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

迁移测试在内存 SQLite 上执行升级、重复升级、降级，并检查 MySQL 离线 SQL。它不能代替真实 MySQL 对所有 DDL 的执行验证。
