# 真实 Agent 冒烟测试

> 在真实 Agent 环境（Claude Code / Copilot CLI）中验证 `/deeprefine` 的 wiki 精化闭环。
> 这些不是自动化脚本——是手动操作手册，附带预期行为检查清单。

---

## 前置条件

1. wiki 项目目录已初始化（`graphify-out/graph.json` 存在，由 `wiki_importer` 生成）
2. `deeprefine-cli` 已安装：`pip install -e .`
3. 对应平台的 skill 已安装：`deeprefine claude install --project`
4. LLM API key 已配置

## 测试用 Wiki 准备

```bash
# 使用 demo-wiki（3 页，快速验证）
cp -r docs/tmp/demo-wiki /tmp/test-wiki

# 使用真实 Obsidian vault（完整验证）
cp -r eval/data/obsidian-vault /tmp/test-wiki

# 导入 wiki → graph.json
cd /tmp/test-wiki
python -c "
from deeprefine_skill.wiki_importer import import_wiki
from pathlib import Path
import_wiki(Path('.'), Path('graphify-out'))
"
```

---

## 测试 A：Claude Code

### A.1 启动

```bash
cd /tmp/test-wiki
claude
```

### A.2 执行 /deeprefine

在 Claude Code 对话中输入：

```
/deeprefine
```

### A.3 检查清单

| # | 检查项 | 预期行为 | 通过? |
|---|--------|---------|:--:|
| 1 | skill 被发现 | Claude Code 自动加载 `/deeprefine` 技能 | □ |
| 2 | history sync | 执行 `deeprefine history sync-memory` | □ |
| 3 | pending list | 执行 `deeprefine history list --pending` | □ |
| 4 | retrieval | 对 wiki 数据执行检索（`wiki_search+k_hop_expansion`） | □ |
| 5 | judge | LLM 输出 `<judge>Yes</judge>` 或 `<judge>No</judge>` | □ |
| 6 | abduct（如需） | 如果 answerable=False，输出 `<abduction>...</abduction>` | □ |
| 7 | refine（如需） | 输出 `<refinement>insert_edge(...)|...</refinement>` | □ |
| 8 | validate | 执行 `deeprefine loop validate` 且通过（无报错） | □ |
| 9 | review | 执行 `deeprefine review`，输出 HIGH/MEDIUM/LOW 报告 | □ |
| 10 | dry-run stop | 停在审查报告阶段，不直接写 graph.json | □ |
| 11 | 用户批准后 apply | 用户回复 "apply" 后执行 `deeprefine apply` | □ |

### A.4 记录

测试完成后，将 Claude Code 对话记录保存到 `eval/results/`。

---

## 测试 B：Copilot CLI

### B.1 启动

```bash
cd /tmp/test-wiki
# 安装 Copilot skill
deeprefine copilot install --project

# 启动 Copilot
copilot
```

### B.2 执行

```
/deeprefine
```

### B.3 检查清单

同上（测试 A 的 11 项）。

---

## 测试 C：Codex / Cursor / Gemini CLI（按需）

参考 README.md 中各平台的 Setup 说明，验证 `/deeprefine` 能正常触发并完成闭环。

---

## 冒烟测试失败怎么办

| 症状 | 可能原因 | 排查方向 |
|------|---------|---------|
| skill 未加载 | 安装路径不对 | `ls .claude/skills/deeprefine/SKILL.md` |
| retrieval 报错 | `wiki_search` 不在白名单 | 检查 `agent_loop.py` 的 `VALID_RETRIEVAL_METHODS` |
| validate 报错 | trace 格式不符合 14 条规则 | 逐条对照 `validate_trace()` 的错误输出 |
| review 全 LOW | wiki evidence 未命中 | 检查 `action_review.py` 的 `_has_wiki_evidence()` |
| apply 被拒绝 | `page_path` 未找到 | 检查 graph.json node 是否有 `page_path` 字段 |
