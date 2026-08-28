# DeepRefine-Skill Evaluation Pipeline

> 本目录包含 DeepRefine-Skill 的评估体系，包括 benchmark 管线、测试数据和冒烟测试。

## 目录结构

```
eval/
├── README.md                    ← 你正在读的文件
│
├── benchmarking/                ← [git: commit]  PR #13 评估管线
│   ├── cli.py                   # 独立 CLI 入口
│   ├── evaluator.py             # 核心评估逻辑
│   ├── graph.py                 # 图操作与对齐
│   ├── metrics.py               # 评估指标实现
│   ├── prepare.py               # 数据集准备
│   ├── report.py                # 报告生成
│   ├── suite.py                 # 测试套件加载
│   └── wiki.py                  # Wiki 格式支持
│
├── suites/                      ← [git: commit]  内置测试套件
│   ├── README.md                # 套件说明
│   └── synthetic-smoke-v1/      # 合成冒烟测试数据
│
├── data/                        ← [git: ignore]  测试数据（不进 git）
│   └── obsidian-icewind-main/   # 真实 Obsidian vault（需手动下载）
│
├── smoke-tests/                 ← [git: commit]  真实 Agent 冒烟测试
│   └── README.md
│
└── results/                     ← [git: ignore]  运行时产物
    └── *.json
```

---

## 一、Benchmark 管线使用

### 1.1 独立 CLI 运行

评估管线已迁移到 `eval/benchmarking/`，作为独立脚本运行：

```bash
# 准备测试套件
python eval/benchmarking/cli.py prepare \
  --suite synthetic-smoke-v1 \
  --output-dir eval/results/synthetic-smoke-v1

# 运行评估
python eval/benchmarking/cli.py evaluate \
  --suite eval/results/synthetic-smoke-v1 \
  --baseline-graph eval/suites/synthetic-smoke-v1/baseline_graph.json \
  --candidate-graph eval/suites/synthetic-smoke-v1/candidate_graph.json \
  --output-dir eval/results/run-001

# 生成报告
python eval/benchmarking/cli.py report \
  --result eval/results/run-001/result.json \
  --output eval/results/run-001/report.md
```

### 1.2 结构评测（structeval）——机械 gold，无 LLM

`structeval` 不依赖套件或人工标注：它用 stdlib `ast` 从 pinned 的 git ref（默认 `v0.2.0`）机械枚举 import 子图 gold（模块实体、模块依赖边、模块→符号 import 边），再对给定 graph.json 打出精确的 P/R/F1。import 关系是机械可判定的，所以这里的 precision/recall 是**精确数**，没有"自出考卷"问题。

```bash
# 评测 v0.2.0 自托管代码图谱（gold 从 tag 现场提取，临时目录用后即删）
python eval/benchmarking/cli.py structeval \
  --graph eval/data/v0.2.0-code-graph/graph.json \
  --output-dir eval/results/v02-structural-baseline

# 为缺失的 gold 边生成 refine 查询集（Stage 2 的输入弹药）
python eval/benchmarking/cli.py structeval \
  --graph eval/data/v0.2.0-code-graph/graph.json \
  --emit-queries eval/results/refine-queries.jsonl \
  --output-dir eval/results/v02-structural-baseline

# Stage 2（refine 之后）：对比 baseline，输出 transitions（恢复/仍缺失/新增未证实）
python eval/benchmarking/cli.py structeval \
  --graph <refined-graph.json> \
  --baseline-result eval/results/v02-structural-baseline/structeval_result.json \
  --output-dir eval/results/v02-structural-candidate
```

指标语义与边界：

- 评测范围只有机械可判定切片：模块实体 + `imports`/`imports_from` 关系边；`calls`/`references`/`rationale_for` 等语义边**不在评测范围**（需抽样人评，属 Stage 3）。
- `--source-tree` 可显式指定源码目录（CI / 无 tag 场景）；默认走 `git archive <tag>` 运行时提取。
- 从 gold 缺失边生成的 refine 查询是 **guided recovery**——Stage 2 的 transitions 必须如实报告为 guided 结果。
- 结果落在 `structeval_result.json` + `structural_report.md`（与套件评测的 `result.json` 不冲突）。

### 1.3 在 Python 中导入

```python
import sys
from pathlib import Path

# 添加 eval 到路径
eval_root = Path(__file__).resolve().parent / "eval"
sys.path.insert(0, str(eval_root))

from benchmarking.evaluator import evaluate_suite
from benchmarking.metrics import precision_recall_f1, answer_exact_match
```

---

## 二、测试数据准备

### 2.1 真实 Obsidian Vault（不进 git）

`eval/data/` 目录已被 `.gitignore` 排除，用于存放真实测试数据：

```bash
# 方式 1: 解压
unzip ~/Downloads/some-vault.zip -d eval/data/obsidian-vault

# 方式 2: clone git 仓库
git clone <vault-repo-url> eval/data/obsidian-vault
```

选择标准：
- 页面数 20-100（太大跑评估太慢，太小不像真实场景）
- 包含 `[[wikilinks]]`，有跨页面引用
- 最好有一定的"缺失链接"——这样精化才有素材

### 2.2 内置测试套件（进 git）

`eval/suites/` 包含小型合成测试套件，用于快速验证：

- `synthetic-smoke-v1/` — 合成冒烟测试数据（baseline/candidate 图 + 预测文件）

这些套件随包分发，但不进入 `site-packages`，仅用于开发测试。

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

## 四、测试文件

`tests/test_benchmark.py` 验证评估管线的核心功能。由于评估代码已迁移到 `eval/benchmarking/`，测试通过仓库根命名空间包导入（`eval/` 刻意不带 `__init__.py`，确保永不进入 wheel）：

```python
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from eval.benchmarking.graph import ...
from eval.benchmarking.evaluator import evaluate_suite
```

`tests/test_structeval.py` 用同样的方式覆盖结构评测（`structeval`）：AST gold 提取（含函数内 import 与相对导入解析）、手检指标、CLI 冒烟与确定论。

---

## 五、设计原则

1. **评估代码不进生产包** — `benchmarking/` 在 `eval/` 下，不随 `pip install` 分发
2. **测试数据不进 git** — `data/` 和 `results/` 已在 `.gitignore` 中
3. **独立脚本，非 CLI 子命令** — 评估管线不注册到 `deeprefine` CLI，两种等价调用：`python eval/benchmarking/cli.py ...`（脚本模式）或仓库根下 `python -m eval.benchmarking.cli ...`（模块模式）
4. **测试套件可追溯** — `suites/` 中的小型合成数据进 git，大型真实数据通过 `prepare.py` 从上游下载
5. **仅源码仓可用（by design）** — wheel 中不含 `eval/`，因此 benchmark 引擎、内置套件与相关测试只能在源码 checkout 中运行；内置套件路径由 `suite.py` 相对 `__file__` 解析

---

## 六、后续开发

| 未来工作 | 代码放哪里 | 说明 |
|---------|-----------|------|
| 新 benchmark 指标 | `eval/benchmarking/metrics.py` | 追加新指标函数 |
| 新测试套件 | `eval/suites/` | 添加新的 suite 目录 |
| 大型 benchmark（100+ 页） | `eval/data/` + `eval/suites/` | 性能 benchmark + 准确率对比 |
| CI pipeline | `.github/workflows/` | 自动跑评估 + smoke test |
| 新 wiki 格式适配器 | `deeprefine_skill/adapters/wiki/` | 实现对应的导入/更新接口 |
| structeval Stage 2 | 端点就绪后跑 refine → `structeval --baseline-result` | LLM refine 恢复缺失 import 边的 guided transitions |
| structeval Stage 3 | 抽样人评脚本 | `calls`/`references`/`rationale_for` 语义边 precision |
