# DeepRefine-Skill: Personal Project Plan

> **这份文档是你的实操路线图，不提交给学长。**
> 对应 proposal.tex，但无页数限制、无评分标准，侧重可执行性、学习目标和 CV 产出。

---

## 1. 项目定位

| 维度 | 说明 |
|------|------|
| **学长看到的** | 把 DeepRefine skill 从 Cursor 移植到 Claude Code + Copilot CLI，改进 harness |
| **你实际在做的** | 设计+实现+交付一个跨平台 agent skill 系统，掌握 agent framework 的工程全链路 |
| **CV 上的定位** | "Built a cross-platform agent skill compiler and productionised an LLM-agent open-source project" |

---

## 2. 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                Reafiner Skill Specification                  │
│  ┌──────────┐ ┌──────────────┐ ┌────────────┐ ┌─────────┐  │
│  │ State    │ │ Prompt       │ │ Validation │ │ Tool    │  │
│  │ Machine  │ │ Templates    │ │ Rules      │ │Contracts│  │
│  │ (8 steps)│ │ (judgement,  │ │ (structural│ │(exec,   │  │
│  │          │ │  abduction,  │ │ + semantic)│ │ read,   │  │
│  │          │ │  refinement) │ │            │ │ write,  │  │
│  │          │ │              │ │            │ │ llm)    │  │
│  └──────────┘ └──────────────┘ └────────────┘ └─────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         ▼                               ▼
┌─────────────────┐             ┌─────────────────┐
│  Skill Compiler  │             │  Skill Compiler  │
│  → Claude Code   │             │  → Copilot CLI   │
└────────┬────────┘             └────────┬────────┘
         │                               │
         ▼                               ▼
┌─────────────────┐             ┌─────────────────┐
│ .claude/skills/ │             │ .github/copilot-│
│ deeprefine/     │             │ instructions.md │
│ SKILL.md        │             │                 │
│ settings.json   │             │                 │
│ (hooks)         │             │                 │
└────────┬────────┘             └────────┬────────┘
         │                               │
         └───────────────┬───────────────┘
                         │
                         ▼
         ┌───────────────────────────────┐
         │       deeprefine-core         │
         │  • trace validation           │
         │  • action parsing & execution │
         │  • graph adapter              │
         │  • structured output checker  │
         └───────────────────────────────┘
```

---

## 3. 分阶段详细计划

### Phase 1: 审计与基线（Week 1–3，~25h）

**目标**：理解当前项目的每一行代码，量化它和 DeepRefine 论文的差距。

#### 1.1 环境搭建（4h）
- [ ] Clone DeepRefine 论文仓库，理解 `autorefiner/src/reafiner.py` 的核心逻辑
- [ ] 通读 DeepRefine 论文（至少理解 Reafiner 算法部分）
- [ ] 在本地跑通 graphify → DeepRefine-Skill 的完整流程
- [ ] 理解项目中的数据流：`graph.json` 的结构、`loop_trace_*.json` 的 schema、`history.jsonl` 的格式

#### 1.2 代码审计（8h）
- [ ] 画出当前项目的模块依赖图
- [ ] 标注每个模块的测试覆盖率（当前为 0%）
- [ ] 找出所有 `print()` → 应改为 structured logging
- [ ] 找出所有 bare `except` → 应改为具体异常处理
- [ ] 标注硬编码路径和假设（如 `graphify-out/`、`../DeepRefine`）
- [ ] 审查 SKILL.md vs. agent_prompts.py 的 prompt 一致性

#### 1.3 基线测量（13h）
- [ ] 准备 20 个测试 query（覆盖：单跳可答、多跳可答、不可答三种场景）
- [ ] 在 Cursor 中执行 `/deeprefine`，记录每个 query 的完整 trace
- [ ] 与论文 Reafiner 的参考 trace 逐步对比
- [ ] 输出基线报告：每步的 compliance rate、常见的 drift 类型

**产出**：
- `docs/phase1-audit.md` — 代码审计报告
- `docs/phase1-baseline.csv` — 20 queries × per-step compliance 数据
- `tests/fixtures/` — 测试用的 graph.json 和 query set

**学习目标**：
- 理解 agent skill 的代码结构模式
- 掌握"对照论文实现审计开源项目"的方法论

---

### Phase 2: 核心硬化（Week 4–6，~45h）

**目标**：设计统一 spec，实现 compiler，建测试体系，改进 harness。

#### 2.1 统一 Specification 设计（10h）
- [ ] 定义状态机（JSON Schema）：
  ```
  states: [INIT, RETRIEVE, JUDGE, RETRIEVE_KHOP, ABDUCE, REFINE, VALIDATE, APPLY, FINISH]
  transitions: 每个 transition 有 guard condition
  ```
- [ ] 提取 verbatim prompt 模板（单一源，YAML）：
  - `judgement_system` / `judgement_user`
  - `abduction_system` / `abduction_user`
  - `refinement_system` / `refinement_user`
- [ ] 定义 Tool Contract（Python Protocol）：
  ```python
  class AgentFramework(Protocol):
      def execute_command(self, cmd: str) -> CommandResult: ...
      def read_file(self, path: str) -> str: ...
      def write_file(self, path: str, content: str) -> None: ...
      def structured_llm_call(self, system: str, user: str, schema: dict) -> dict: ...
  ```
- [ ] 定义验证规则 DSL（从 `validate_trace()` 泛化）

#### 2.2 Skill Compiler 实现（12h）
- [ ] 实现 `SpecParser`：YAML → 内部数据模型
- [ ] 实现 `ClaudeCodeEmitter`：Spec → `.claude/skills/deeprefine/SKILL.md` + `settings.json`
- [ ] 实现 `CopilotEmitter`：Spec → `.github/copilot-instructions.md`
- [ ] 实现 `deeprefine compile` CLI 子命令
- [ ] 单元测试：验证两个 emitter 产出的文件可被各自框架解析

#### 2.3 测试体系建设（12h）
- [ ] Unit tests: `test_agent_loop.py`（trace 验证逻辑，~20 cases）
- [ ] Unit tests: `test_agent_graph.py`（action 解析+执行，~15 cases）
- [ ] Unit tests: `test_history.py`（CRUD + mark_refined，~10 cases）
- [ ] Integration tests: `test_tool_contract.py`（验证 Tool Contract 在真实环境可用）
- [ ] Functional tests: `test_e2e_trace.py`（完整 8 步 trace 的 golden file 对比）
- [ ] 目标覆盖率：核心模块 ≥80%，整体 ≥60%

#### 2.4 Harness 改进实现（11h）
- [ ] **机制 A — Deterministic k-hop expansion**（3h）：
  - 在 `agent_loop.py` 中实现 `expand_khop(entities, graph_json, hop=1)` 
  - 不再依赖 LLM 决定"从哪些实体扩展"
- [ ] **机制 B — Structured output enforcement**（4h）：
  - 对 `<judge>` 输出做正则匹配，不匹配则 reject + retry
  - 对 `<abduction>` 输出做标签完整性检查
  - 对 `<refinement>` 输出做 action 白名单验证（只允许 insert_edge/delete_edge/replace_node）
- [ ] **机制 C — Inline validation checkpoints**（4h）：
  - 在状态机的每个 transition 插入验证 hook
  - 验证失败 → 立即 abort（不等到最后）
  - 记录 abort reason 到 trace（方便调试）

**产出**：
- `deeprefine_skill/spec/` — specification 模块
- `deeprefine_skill/compiler/` — compiler 模块
- `tests/` — 完整测试套件
- `.github/workflows/ci.yml` — CI skeleton

**学习目标**：
- 掌握 compiler 设计模式（IR → multi-target emission）
- 学会为 LLM-agent 系统设计测试策略
- 理解"多少控制应该从 LLM 手中拿走"的工程权衡

---

### Phase 3: 多平台部署（Week 7–10，~55h）

**目标**：在 Claude Code 和 Copilot CLI 上实现可用的 `/deeprefine`，完成跨平台验证。

#### 3.1 Claude Code Adapter — P0（20h）
- [ ] 编写 Claude Code 版 SKILL.md（基于 compiler 输出，手工打磨）
  - 声明 `allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]`
  - 利用 Claude Code 的 Task tool 做并行步骤（graphify query 和 graph.json read 可并行）
- [ ] 配置 `.claude/settings.json` hooks：
  - `PreToolUse` → `deeprefine apply` 前强制检查 backup
  - `PostToolUse` → `deeprefine apply` 后自动写 audit log
  - `Error` → deeprefine 相关错误时注入恢复指引
- [ ] 在 Claude Code 中端到端测试：
  - [ ] 正常流程：hop1 No → hop2 Yes → abduction → refinement → apply
  - [ ] 早退流程：hop1 Yes → early exit
  - [ ] 边界情况：graph.json 不存在、refinement 格式错误、空 query
- [ ] 记录所有 hook 触发行为的正确性

#### 3.2 Copilot CLI Adapter — P1（15h）
- [ ] 研究 Copilot CLI 的指令格式和能力边界
- [ ] 编写 `.github/copilot-instructions.md`
- [ ] 如 Copilot CLI 不支持 hook/fine-grained tool control，如实记录为框架能力差距
- [ ] 端到端测试（同 Claude Code 的 test cases）
- [ ] 与 Claude Code trace 逐 step 对比，标注 divergence 来源

#### 3.3 跨平台功能验证（10h）
- [ ] 构建验证 harness：`deeprefine validate-cross --trace-a ... --trace-b ...`
  - 比对：步骤数一致、每步的 judgement 结果相同、refinement actions 等价
  - 允许微小的格式差异（如 evidence 字段的截断），但结构必须一致
- [ ] 在 20-query suite 上跑两个框架，输出 divergence matrix
- [ ] 对每个 divergence 做 root-cause 分类：
  - Type A: 框架能力缺失（如 Copilot CLI 不能执行某条 Bash 命令）
  - Type B: LLM 行为差异（同一 prompt 在两个平台上推理不同）
  - Type C: Prompt 理解偏差（框架对 prompt 的注入方式不同）

#### 3.4 CI/CD 完善（10h）
- [ ] `.github/workflows/ci.yml`：
  ```yaml
  on: [push, pull_request]
  jobs:
    lint:     ruff check + ruff format --check
    type:     mypy deeprefine_skill/
    unit:     pytest tests/unit/ -v --cov
    integration: pytest tests/integration/ -v
    functional: pytest tests/functional/ -v  # 需要 graphify 环境
  ```
- [ ] `.github/workflows/publish.yml`：tag push → build → PyPI publish
- [ ] pre-commit hooks: ruff + mypy

**产出**：
- `.claude/skills/deeprefine/SKILL.md` + `.claude/settings.json`
- `.github/copilot-instructions.md`
- `deeprefine_skill/validation/cross_platform.py`
- CI/CD pipeline（绿勾）
- 跨平台 divergence matrix

**学习目标**：
- 掌握至少两个主流 agent framework 的 skill 开发
- 学会设计跨平台软件的验证策略
- CI/CD for AI projects 的实践经验

---

### Phase 4: 文档与收尾（Week 11–13，~25h）

**目标**：让这个项目可以被别人（和未来的你）理解、使用、和扩展。

#### 4.1 文档（10h）
- [ ] `README.md` 重写：
  - Quick start（Claude Code 用户）
  - Quick start（Copilot CLI 用户）
  - 架构概览图
  - 如何添加新 framework target 的指南
- [ ] `CONTRIBUTING.md`：开发环境搭建、测试运行、PR 流程
- [ ] API docs：`deeprefine-core` 的公共接口（用 docstring + mkdocs 或 sphinx）
- [ ] 每个 adapter 的安装指南（含截图/GIF）

#### 4.2 打包与发布（5h）
- [ ] `pyproject.toml` 添加 extras：
  ```toml
  [project.optional-dependencies]
  claude = []
  copilot = []
  dev = ["pytest", "pytest-cov", "ruff", "mypy", "pre-commit"]
  ```
- [ ] 发一个 release v0.2.0 到 PyPI
- [ ] 在 README 上加 PyPI badge + CI badge

#### 4.3 Thesis（10h）
- [ ] 结构（参考 proposal 的四个 phase）：
  1. Introduction — agent skill 作为新兴软件制品，DeepRefine 案例
  2. Background — Reafiner 算法、graphify、当前 SKILL.md 的局限
  3. Approach — 统一 spec、compiler、三种 harness 机制
  4. Implementation — Claude Code adapter、Copilot CLI adapter
  5. Evaluation — 跨平台对比、harness 机制的 ablation
  6. Discussion — 经验教训、框架选择建议、未来工作
- [ ] 重点在 Chapter 5 和 6——这是你区别于学长论文的原创贡献

**产出**：
- 完整文档站
- PyPI release v0.2.0
- 最终论文

**学习目标**：
- OSS 项目的完整发布流程
- 技术写作能力（API docs + thesis）
- 把一个项目"讲清楚"的能力（面试关键）

---

## 4. 学习目标清单

完成这个项目后，你在面试中能自信地说"我做过"的技能：

| 技能 | 对应阶段 | 大厂 JD 关键词 |
|------|---------|--------------|
| Agent framework skill 开发 | Phase 3 | "Experience building on Claude/OpenAI/Copilot platforms" |
| Compiler/IR 设计 | Phase 2 | "System design for multi-target code generation" |
| 非确定性系统测试 | Phase 2 | "Testing strategies for LLM-based systems" |
| CI/CD for AI projects | Phase 3 | "CI/CD, GitHub Actions, automated testing" |
| Cross-platform validation | Phase 3 | "Cross-platform software quality assurance" |
| Python 项目工程化 | Phase 2-4 | "Production Python development, packaging, docs" |
| OSS contribution | Phase 4 | "Open-source contribution experience" |
| 技术写作 | Phase 4 | "Technical documentation, API design" |

---

## 5. CV 子弹映射

项目完成后，你可以按投递岗位挑选以下子弹：

### Agent / AI Platform 岗位

```
DeepRefine-Skill — Cross-Platform Agent Skill Compiler
Open-source contributor | Python, Claude Code SDK, Copilot CLI

• Designed a unified agent-skill specification (state machine, tool contracts,
  validation schemata) and built a compiler that emits native skill artefacts for
  Claude Code and GitHub Copilot CLI, eliminating per-platform manual rewriting
  
• Implemented three incremental harness mechanisms (deterministic k-hop expansion,
  structured-output enforcement, inline validation checkpoints) that reduced LLM
  protocol deviation in an 8-step KG refinement agent loop

• Built a cross-platform functional validation harness that verifies behavioural
  equivalence of identical agent protocols across hook-based (Claude Code) and
  instruction-based (Copilot CLI) frameworks, with root-cause decomposition of
  framework-induced execution divergence
```

### ML Engineering / AI Reliability 岗位

```
DeepRefine-Skill — Production Engineering for LLM-Agent Systems
Open-source contributor | Python, pytest, GitHub Actions, PyPI

• Hardened a research-demo agent-skill codebase: introduced test pyramid (unit →
  integration → trace-level functional) covering parsing, validation, tool-contract
  compliance, and end-to-end protocol fidelity for non-deterministic LLM outputs

• Established CI/CD pipeline (lint → type-check → unit → integration → functional)
  with automated cross-platform agent behavioural testing

• Implemented error-recovery patterns for agent protocols: format-aware LLM retry,
  automatic rollback on failed graph mutations, degraded-mode structured logging
```

### General SWE 岗位

```
DeepRefine-Skill — Multi-Platform Agent Skill Development
Open-source contributor | Python, Claude Code, Copilot CLI, GitHub Actions

• Ported an LLM-agent skill system from single-framework (Cursor) to multi-framework
  (Claude Code, Copilot CLI) via a compiler architecture, reducing per-platform
  adaptation cost from manual rewrite to automated emission

• Introduced test automation (80%+ coverage), CI/CD, structured logging, and PyPI
  packaging to an open-source research project

• Authored framework-specific user guides and a contributor guide for adding new
  agent-platform targets
```

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解策略 |
|------|-----|------|---------|
| Copilot CLI skill 系统不成熟，无法实现完整 adapter | 中 | 中 | 降级为"如实记录能力差距"（这本身是 RQ3 的有效发现），不硬上 |
| Claude Code skill/hook 行为与文档不一致 | 低 | 中 | Phase 3 一开始先做 smoke test，确认基础能力可用再深入 |
| 20 query 的基线数据不够显著 | 中 | 低 | 扩展到 30 query + 3 个 KG domain |
| 150h 不够 | 中 | 高 | Copilot CLI adapter 做 MVP（只覆盖核心路径），不做完整测试 |
| DeepRefine 仓库依赖过重（conda/vLLM/FAISS） | 高 | 低 | 基线测量用 SKILL.md agent 模式（零额外依赖），不硬要求跑 CLI 模式 |

---

## 7. 里程碑时间线

```
Week 1  ██ 环境搭建 + 论文精读
Week 2  ██ 代码审计完成
Week 3  ██ 基线数据采集完成 → D1 交付（给学长看进度）
────────── Phase 1 完成 ──────────

Week 4  ██ Spec 设计完成
Week 5  ██ Compiler 实现 + 单元测试
Week 6  ██ Harness 三种机制实现 + CI skeleton → D2 交付
────────── Phase 2 完成 ──────────

Week 7  ██ Claude Code adapter 框架搭建
Week 8  ██ Claude Code adapter 端到端跑通
Week 9  ██ Copilot CLI adapter 实现 + 测试
Week 10 ██ 跨平台验证完成 + CI/CD 完善 → D3+D4 交付
────────── Phase 3 完成 ──────────

Week 11 ██ 文档 + 打包
Week 12 ██ Thesis 撰写
Week 13 ██ 最终修改 + 答辩准备 → D5+D6 交付
────────── Phase 4 完成 ──────────
```
