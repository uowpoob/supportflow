# 向量入库

入口为 `../src/supportflow/retrieval/resource2chunks.py`。

## 配置与执行

在 `.env` 中配置 `DASHSCOPE_API_KEY`、`DASHSCOPE_BASE_URL`、
`EMBEDDING_MODEL`、`EMBEDDING_DIM`、`MILVUS_URI`、`DB_NAME`、`COLLECTION`。
向量模型和 Milvus 集合共用 `EMBEDDING_DIM`；当前模型为 `text-embedding-v4`。

在项目根目录先预览文档和片段数量（不调用外部服务）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m supportflow.retrieval.resource2vector --dry-run
```

执行向量化和入库（会调用配置的 Embedding API，并写入 Milvus）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m supportflow.retrieval.resource2vector
```

执行顺序：读取 `policies/` 和 `data/` → 按二级标题切分 → 检查集合结构 →
生成向量（每次 API 请求最多 10 条）→ 校验全部片段和向量 → 每批最多 100 条 upsert →
flush → 用强一致性查询核对本次片段的记录数。发生异常时关闭客户端并报错退出。

## 存储字段

| 字段 | 用途 |
| --- | --- |
| `chunk_id` | VARCHAR 主键，例如 `PRD-103-sony-wh1000xm5#1.5`；关闭自动 ID |
| `vector` | FLOAT_VECTOR，长度等于 `EMBEDDING_DIM`，COSINE 索引 |
| `content` | 含文档标题、条款标题的完整片段文本 |
| `document_id` / `title` / `section` / `source` / `category` | 原文档与条款来源 |
| `embedding_model` / `embedding_dim` | 生成向量时使用的模型与维度 |

主键和向量字段显式建表，其他字段通过 Milvus 动态字段保存。
已有集合需要相容的字符串主键、向量维度及动态字段配置；不匹配时报错并保留原集合。

## 重复执行与边界

- 同一 `chunk_id` 使用 upsert 更新，重复运行不增加相同 ID 的记录。
- 每次重新生成当前全部片段的向量，尚未实现向量缓存或增量判断。
- 源文件中删除或改编号的条款，不会自动从数据库清理；本命令不是全量镜像同步。
- 批次之间没有整体事务。中途失败时，先前成功的批次仍然保留，可修复后重跑。
- 更换向量模型时应使用新的集合名，即使维度相同，也不应混用不同模型的向量。
- 已实现向量召回并接入 LangGraph 检索节点，使用方式见 [向量召回](vector-retrieval.md)。

离线验证：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_retrieval_clients.py tests/test_retrieval_loader.py tests/test_retrieval_storage.py -q -p no:cacheprovider
```
