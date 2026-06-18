# Reafiner 源码阅读笔记

> 源码：`DeepRefine/autorefiner/src/reafiner.py`（1299 行）
> 对照：`deeprefine_skill/` 下的 agent 模式实现

---

## 目录

1. [整体结构：两个 dataclass + 一个 class](#1-整体结构)
2. [refine() 主循环](#2-refine-主循环)
3. [\_answerable\_judgement — LLM 判断](#3-_answerable_judgement)
4. [\_error\_abduction — 错误诊断](#4-_error_abduction)
5. [\_kg\_refinement\_action — 生成修正动作](#5-_kg_refinement_action)
6. [\_construct\_subgraph — k-hop BFS](#6-_construct_subgraph)
7. [KG 写操作](#7-kg-写操作)
8. [关键设计决策汇总](#8-关键设计决策汇总)

---

## 1. 整体结构

`reafiner.py` 由 **两个 dataclass + 一个 class** 组成：

### 两个 dataclass（纯数据结构）

| Dataclass | 行号 | 用途 | 关键字段 |
|-----------|------|------|----------|
| `RetrievalStepResult` | L44-55 | 单次 hop 的快照 | `num_hops`, `retrieved_subgraph`, `answerable`, `answer` |
| `RefinementResult` | L57-69 | 整个 refine 过程的完整档案 | `query`, `interaction_history`（一串 RetrievalStepResult）, `error_abduction_reason`, `refinement_action_list` |

`RetrievalStepResult` 是中间产物，`RefinementResult` 是最终输出。关系：
```
RefinementResult.interaction_history = [RetrievalStepResult, RetrievalStepResult, ...]
```

### 一个 class（执行引擎）

`Reafiner`（L72-1297）是所有逻辑的载体：

| 分类 | 方法 | 行号 |
|------|------|------|
| **对外接口** | `refine(query)` | L194 |
| **LLM 调用** | `_answerable_judgement`, `_error_abduction`, `_kg_refinement_action` | L681, L728, L842 |
| **检索** | `_encode_query`, `_construct_subgraph`, `_prune_subgraph_embd`, `_prune_subgraph_llm`, `_compute_query_edge_scores` | L388, L1250, L516, L402, L460 |
| **KG 写** | `_insert_edge`, `_delete_edge`, `_replace_node` | L1007, L1103, L1157 |
| **工具** | `_parse_action_string`, `_get_node_id`, `_safe_sanitize` | L789, L1230, L1241 |

数据和行为分离：两个 dataclass 只装数据，Reafiner 只执行逻辑。这是 dataclass 的设计意图——不带行为的结构体。

### 1.1 data 字典：Reafiner 的输入

`data` 是一个巨大的 dict，在构造 `Reafiner` 时传入。它把整个知识图谱的所有表示形式打包在一起。分三层理解：

#### 图结构层

| 字段 | 类型 | 说明 |
|------|------|------|
| `KG` | `networkx.DiGraph` | 知识图谱本体，有向图。节点=entity/passage，边=relation。`__init__` 中通过 `subgraph(self.node_list)` 过滤掉 passage 节点 |
| `node_list` | `list[str]` | entity 节点的内部 ID 列表（不含 passage）。用于 k-hop BFS 时的合法性判断 |
| `edge_list` | `list[tuple]` | 所有边的 `(head_id, tail_id)` 列表。用于 embedding 裁剪时定位边的全局索引 |

#### 向量层

| 字段 | 类型 | 说明 |
|------|------|------|
| `node_embeddings` | `np.ndarray` | 每个 entity 节点的向量表示（如 768 维浮点数组） |
| `edge_embeddings` | `np.ndarray` | 每条边的向量表示 |
| `node_faiss_index` | `faiss.Index` | 节点向量索引，O(log N) 最近邻搜索 |
| `edge_faiss_index` | `faiss.Index` | 边向量索引，用于检索：query 编码 → 搜索 top-k 最相关边 |
| `text_faiss_index` | `faiss.Index` | 文本向量索引（retriever 中使用） |
| `text_dict` | `dict` | 文本 ID → 文本内容 |

**embedding 的作用**：将符号化的 KG 映射到语义空间。用户 query "Who discovered relativity?" 和 KG 中的 triple `[Einstein] developed [General Relativity]` 字符串不完全匹配，但向量空间中距离很近。

**FAISS 的作用**：Facebook AI Similarity Search，高性能向量搜索引擎。`retriever.retrieve(query, topN=10)` 的内部流程是：query → encoder → 向量 → `edge_faiss_index.search()` → top-10 最相关 triple。

#### 映射层

| 字段 | 类型 | 说明 |
|------|------|------|
| `node_id_to_attr_id` | `dict` | 实体名称 → 节点内部 ID（如 `"Albert Einstein" → "n123"`），`__init__` 中从 `KG.nodes[n]['id']` 构建 |
| `edge_faiss_id_to_list_idx` | `dict` | FAISS 内部 ID → `edge_list` 中的下标。初始恒等映射 `{0:0, 1:1, ...}`，增量更新后不恒等 |
| `node_faiss_id_to_list_idx` | `dict` | 同上，节点的 FAISS ID → `node_list` 下标 |
| `text_faiss_id_to_list_idx` | `dict` | 同上，文本的 FAISS ID → `text_dict` 下标 |

**为什么需要映射表？** FAISS 索引的增删操作会在 ID 空间中留下空洞（`remove_ids` 不压缩）。insert 在末尾追加，delete 产生空缺 → FAISS ID 和 list 下标不再对齐，需要映射表维护对应关系。

#### 与 Agent 模式的对比

| 概念 | CLI 模式（reafiner.py） | Agent 模式（deeprefine_skill） |
|------|------------------------|-------------------------------|
| KG | `networkx.DiGraph` + FAISS | `graph.json`（JSON 文件） |
| 检索 | FAISS 向量搜索 | `graphify query`（agent 调另一个 skill） |
| 图操作 | 内存中 `add_edge`/`remove_edge` | `deeprefine apply` 写 JSON |
| embedding | 预编码 + 增量更新 | 不需要——LLM 直接读 triple 文本判断 |
| 映射表 | 三张 `faiss_id_to_list_idx` | 不需要 |

Agent 模式只需理解**控制流**（何时 judge/abduce/early exit）和 **prompt 格式**（`<judge>`/`<abduction>`/`<refinement>` XML 标签）。

---

## 2. refine() 主循环

（待补充）

## 3. _answerable_judgement

（待补充）

## 4. _error_abduction

（待补充）

## 5. _kg_refinement_action

（待补充）

## 6. _construct_subgraph

（待补充）

## 7. KG 写操作

（待补充）

## 8. 关键设计决策汇总

（待补充）
