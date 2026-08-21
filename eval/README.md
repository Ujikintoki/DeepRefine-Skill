# DeepRefine-Skill 评估与工程硬化

> 本目录包含 wiki 精化的评估数据、benchmark 脚本、真实 Agent 冒烟测试，以及工程硬化路线图。
> `data/` 和 `results/` 不进 git，脚本进 git。

## 目录结构

```
eval/
├── README.md                    ← 你正在读的文件
│
├── data/                        ← [git: ignore]  测试数据
│   ├── .gitkeep
│   ├── autoschema_kg_md/        → symlink 到 ../../DeepRefine/AutoSchemaKG/example/example_data/md_data/
│   └── obsidian-vault/          ← 你找的真实 Obsidian vault（clone 或解压到这里）
│
├── benchmarks/                  ← [git: commit]  eval 脚本
│   ├── kg_structure.py          # 图结构指标：精化前后连通性、边密度、平均路径等
│   └── refinement_recall.py     # 精化召回率：删 N 条 link → 精化 → 测恢复了多少
│
├── smoke-tests/                 ← [git: commit]  真实 Agent 冒烟测试
│   ├── README.md                # 冒烟测试说明与执行步骤
│   ├── test_claude_code.sh      # Claude Code 调用 /deeprefine
│   └── test_copilot_cli.sh      # Copilot CLI 调用 /deeprefine
│
└── results/                     ← [git: ignore]  运行时产物
    └── YYYY-MM-DD_baseline.json
```

---

## 一、测试数据的准备与接入

### 1.1 AutoSchemaKG md_data

```bash
cd eval/data
ln -s ../../../../DeepRefine/AutoSchemaKG/example/example_data/md_data autoschema_kg_md
```

内容：2 个 Apple 报告（~464KB），链接格式为 `[text](#anchor)`。这些是同页面内跳转的锚点链接，`wiki_importer._is_internal_wiki_link()` 会正确过滤（`#` 开头的 URL 不被视为跨页面 wiki link）。

### 1.2 真实 Obsidian vault

```bash
cd eval/data
# 方式 1: clone git 仓库
git clone <vault-repo-url> obsidian-vault

# 方式 2: 解压
unzip ~/Downloads/some-vault.zip -d obsidian-vault
```

选 vault 的标准：
- 页面数 20-100（太大跑精化太慢，太小不像真实场景）
- 包含 `[[wikilinks]]`，有跨页面引用
- 最好有一定的"缺失链接"（同一主题的页面没有互链）——这样精化才有素材

---

## 二、Benchmark 脚本

### kg_structure.py — 图结构指标

不依赖真实 LLM，纯 networkx 计算。对精化前后 graph.json 各跑一次，对比：

| 指标 | 含义 | 精化后期望方向 |
|------|------|:--:|
| `avg_in_degree` / `avg_out_degree` | 节点平均入度/出度 | ↑ 更多链接 |
| `edge_density` | 边密度（实际边 / 可能最大边） | ↑ 图更连通 |
| `reciprocal_edge_fraction` | 双向边比例 | ↑ 双向链接更完整 |
| `avg_shortest_path_length` | 平均最短路径（≤3 hop） | ↓ 信息更容易到达 |
| `num_connected_components` | 弱连通分量数 | ↓ 孤立内容更少 |
| `relation_entropy` | 关系类型熵 | ↑ wiki 场景不适用（全是 `links_to`） |

### refinement_recall.py — 精化召回率

**方法**：
1. 从一个完整 wiki 出发，记录所有已有的 `[[link]]` 作为 ground truth
2. 故意删除 N%（如 20%）的 `[[link]]`，构造"不完整 KG"
3. 跑 importer → 检 索→ judge → abduct → refine → update 闭环
4. 测量：被删除的链接有多少被 LLM 正确恢复（Recovery Rate）
5. 测量：LLM 建议的修复动作中，正确/错误/多余的比例

**为什么需要调用真实 LLM**：
图结构指标可以在本地跑（零 API 调用），但召回率测试必须走完整的精化闭环——需要 LLM 做 judge + abduct + refine。这是评估体系的核心指标。

**运行**：
```bash
cd eval/benchmarks
export OPENAI_API_KEY=sk-...
python refinement_recall.py --wiki-dir ../data/obsidian-vault --delete-rate 0.2
```

---

## 三、真实 Agent 冒烟测试

### 3.1 什么是冒烟测试？

手动（或脚本辅助）在真实 Agent 中跑一次 `/deeprefine`，验证：
- 平台安装正确（`deeprefine <platform> install`）
- wiki import + retrieval 在真实 agent 环境中可用
- LLM 能正确理解 wiki 检索结果并完成 judge → abduct → refine 循环
- 安全闸门生效（dry-run 先出报告，不直接写 graph.json）

### 3.2 Claude Code 冒烟测试

前置：`deeprefine claude install --project` 已完成。

```bash
# 启动 Claude Code，在 wiki 项目目录下
claude

# 在 Claude Code 中执行：
> /deeprefine
```

预期行为：
1. LLM 自动运行 `deeprefine history sync-memory`
2. 对 pending query 执行 wiki 检索 → judge → abduct → refine
3. 停在 dry-run 模式，展示 HIGH/MEDIUM/LOW 审查报告
4. 不直接修改 graph.json

### 3.3 Copilot CLI 冒烟测试

```bash
# 启动 Copilot CLI
copilot

# 执行
> /deeprefine
```

预期同上。

---

## 四、硬化工作：代码放置位置

硬化改动**全部在 `deeprefine_skill/` 下**，直接改生产代码文件。每一项都是 5-20 行的追加式改动，不新增文件，不变 API。

| 优先级 | 任务 | 改哪个文件 | 改什么 | 行数 |
|:--:|------|-----------|--------|:--:|
| ⭐⭐⭐ | 自环过滤 | `wiki_importer.py` | `build_graph()` Pass 2 中 `if source_id == target_id: continue` | ~3 |
| ⭐⭐⭐ | 悬挂链接占位节点 | `wiki_importer.py` | Pass 1 后未匹配的 label → 生成 ghost node（`status: "dangling"`） | ~15 |
| ⭐⭐⭐ | 动作上限 | `agent_graph.py` | `parse_refinement_block()` 解析后 `if len(actions) > 20: raise` | ~8 |
| ⭐⭐⭐ | label_index 持久化 | `wiki_importer.py` | `build_graph()` 结束前写 `label_index.json` sidecar | ~15 |
| ⭐⭐⭐ | 自环过滤（Obsidian 常见） | `wiki_importer.py` | 页面引用自身在 Obsidian 中很常见，避免噪声边 | ~3 |
| ⭐⭐ | 边上下文捕获 | `wiki_importer.py` | extraction 时保留 [[link]] 前后 ±50 chars → `edge["context"]` | ~20 |
| ⭐⭐ | 精化上下文注入 | `wiki_retrieval.py` | `retrieve()` 返回对象加 `page_snippets` | ~25 |
| ⭐⭐ | 缓存 `_find_node()` | `wiki_update.py` | `apply_refinement_with_wiki_update()` 开头预建 label→node 索引 | ~10 |
| ⭐ | 实时评估反馈 | TBD | `action_review.py` 加 wiki 语义证据（在页面内容中搜 relation 对应文本） | ~30 |

### 硬化的正确位置

```
deeprefine_skill/
├── wiki_importer.py       ← 自环、悬挂、label_index、边上下文
├── wiki_update.py          ← _find_node 缓存
├── wiki_retrieval.py       ← 精化上下文注入
├── agent_graph.py          ← 动作上限
└── action_review.py        ← wiki 语义证据（低优先级）
```

**为什么不在 `eval/` 下**：这些不是实验性代码——是生产代码的质量改进。任何用户跑 wiki import 都应该受益于自环过滤和悬挂占位。

---

## 五、后续开发预留空间

| 未来工作 | 代码放哪里 | 说明 |
|---------|-----------|------|
| 新 wiki 格式适配器（Notion, Logseq） | `deeprefine_skill/` 新增文件 | 实现 `import_wiki()` / `apply_refinement_with_wiki_update()` 对应接口 |
| CLI 自动派发（wiki vs code） | `cli.py` | 根据 node 字段自动选 importer/update backend |
| 大型 benchmark（100+ 页） | `eval/benchmarks/` | 性能 benchmark + 准确率对比 |
| CI pipeline | `.github/workflows/` | 自动跑单元测试 + smoke test |
| SKILL.md 模板化（YAML spec → Jinja2） | `scripts/` 或独立工具 | 当平台数 > 6 时考虑 |
