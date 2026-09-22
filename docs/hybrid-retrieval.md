# 混合召回与 RRF

图节点 `retrieve_knowledge` 现在调用 `retrieval/hybrid.py` 的 `retrieve_hybrid()`：
同时发起 Milvus 向量召回与本地 BM25 召回，再调用 `retrieval/rrf.py` 的纯函数融合结果。
不写数据库、不生成回答，不调用重排模型。

## 调用与参数

```python
from supportflow.retrieval.hybrid import retrieve_hybrid

chunks = await retrieve_hybrid(
    "WH-1000XM5 有线模式",
    candidate_k=20,  # 每路最多召回 20 个候选
    top_k=5,        # 融合后最终最多返回 5 个片段
    rrf_k=60,       # 名次平滑常数，与候选数量不同
)
```

```powershell
.\.venv\Scripts\python.exe -X utf8 -m supportflow.retrieval.hybrid "WH-1000XM5 有线模式" --candidate-k 20 --top-k 5 --rrf-k 60
.\.venv\Scripts\python.exe -X utf8 -m supportflow.retrieval.hybrid "无理由退货运费" --category policies
```

| 参数 | 默认 | 含义 |
| --- | --- | --- |
| top_k | 5 | 最终片段数，整数 1～100 |
| candidate_k | 20 | 每路召回窗口，整数 top_k～100 |
| rrf_k | 60 | RRF 平滑常数，正整数 |
| min_score | 0.5 | 仅向量召回使用的 COSINE 门槛，范围 -1～1 |
| category | None | 两路共同过滤 data / policies；默认不限制 |
| document_ids | None | 两路共同限定文档 ID；空列表直接返回 [] |

命令行用 `--min-score`、`--category` 和可重复的 `--document-id`。
先完成所有参数校验，再调用两路检索。更大的候选窗口会增加计算量，默认值未经过质量评测调优。

## RRF 计算

对每个片段 d，计算 `RRF(d) = Σ 1 / (rrf_k + rank_i(d))`。
名次从 1 开始，没有出现在某一路中，则该路贡献为 0；两路权重相同。
输入列表已经按各路相关性降序排列，不重新比较或归一化它们的原始分数。

例如向量排序 `[A, B]`，BM25 排序 `[C, B]`，`rrf_k=60`：

- A：`1/61`。
- B：`1/62 + 1/62`。
- C：`1/61`。

B 排第一；A、C 同分时按 `chunk_id` 升序排列。每路先按 `chunk_id` 去重，
再给剩余候选从 1 编号，避免重复记录额外加分。两路全部贡献累加后才截取最终 Top-K。

返回结构与单路召回一致：`document_id`、`chunk_id`、`title`、`section`、`source`、
`category`、`content`、`score`。此处 `score` 已替换为 RRF 分数；不保留原始分数。
RRF 分数仅用于排序，不是相似度或概率，也不应用向量的 0.5 门槛。
函数创建新的结果字典，不修改输入或 BM25 缓存。

也可以直接验证纯融合函数，不访问任何检索服务：

```python
from supportflow.retrieval.rrf import reciprocal_rank_fusion

fused = reciprocal_rank_fusion([vector_chunks, bm25_chunks], top_k=5, rrf_k=60)
```

## 故障与图状态

| 两路结果 | 返回行为 | retrieval_status |
| --- | --- | --- |
| 都正常，至少一路有候选 | 融合非空候选 | ready |
| 都正常且都为空 | [] | empty |
| 一路失败，另一路有候选 | 用正常一路的名次计算 RRF，记录降级日志 | ready |
| 一路失败，另一路为空 | 抛 RetrievalUnavailable | unavailable |
| 两路都失败 | 抛 RetrievalUnavailable | unavailable |

失败的那一路不会得到任何 RRF 贡献。图状态 `ready` 表示有本轮证据，
不保证两路都健康；单路故障目前记录在日志中。取消请求与未包装的代码错误不作为正常降级吞掉。
没有检索问题时节点直接返回 `empty`，不启动两路查询。每轮仍整体替换证据列表，避免复用旧证据。

## 语料边界

两路使用相同切分规则和 `chunk_id`。相同 ID 的正文及来源保留输入列表中首次出现的版本；
混合入口固定把向量结果放前面，不受异步完成顺序影响。这是确定性选择，不是版本新旧判断。
RRF 不检测或修复语料版本差异：修改本地资料后，需要刷新 BM25 缓存并同步向量库；
向量入库尚不清理删除条款，历史片段仍可能被召回。

RRF 只融合召回排名，不判断片段能否回答问题；最终 Agent 仍须核对型号、条款适用范围与正文。
目前没有额外的 rerank 模型。

算法参考：[Elastic RRF 说明](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion)。
