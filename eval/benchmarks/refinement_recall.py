#!/usr/bin/env python3
"""精化召回率评估：删除已知链接 → 精化 → 测量恢复率。

方法:
  1. 导入 wiki，记录所有 [[link]] 作为 ground truth
  2. 随机删除 N% 的 [[link]]（从 .md 源文件中物理移除）
  3. 重新导入 → 跑精化闭环 → 测量修复动作中恢复了多少被删除的链接

需要真实 LLM API（judge + abduct + refine）。

用法:
    python eval/benchmarks/refinement_recall.py \
        --wiki-dir ../data/obsidian-vault \
        --delete-rate 0.2 \
        --api-key sk-...
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import sys
import tempfile
from pathlib import Path


# --- Step 1: 准备"不完整 KG"（静默删除已知链接） ---

def record_ground_truth(wiki_dir: Path) -> dict[str, set[str]]:
    """扫描 wiki 目录，记录每个页面的 [[link]] 目标作为 ground truth。

    Returns:
        {page_stem: {target_label, ...}}
    """
    from deeprefine_skill.wiki_importer import extract_links
    truth: dict[str, set[str]] = {}
    for f in sorted(wiki_dir.iterdir()):
        if not f.is_file() or f.suffix.lower() not in {".md", ".markdown", ".txt"}:
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        links = extract_links(text)
        if links:
            truth[f.stem] = set(links)
    return truth


def delete_links_from_file(filepath: Path, targets_to_delete: set[str]) -> int:
    """从 .md 文件中物理移除指定的 [[link]] 行。返回删除数。"""
    import re

    text = filepath.read_text(encoding="utf-8", errors="ignore")
    deleted = 0
    for target in targets_to_delete:
        escaped = re.escape(target)
        pattern = re.compile(r"\[\[" + escaped + r"(?:\|[^\]]*)?(?:\#[^\]]*)?\]\]")
        new_text, count = pattern.subn("", text)
        if count:
            text = new_text
            deleted += count
    if deleted:
        filepath.write_text(text, encoding="utf-8")
    return deleted


def prepare_degraded_wiki(wiki_dir: Path, truth: dict, delete_rate: float) -> Path:
    """复制 wiki 到临时目录，随机删除 delete_rate 比例的 [[links]]。

    Returns: 临时目录路径
    """
    import shutil

    tmp = Path(tempfile.mkdtemp(prefix="eval-wiki-"))
    shutil.copytree(wiki_dir, tmp, dirs_exist_ok=True)

    all_links = [(src, tgt) for src, tgts in truth.items() for tgt in tgts]
    num_delete = max(1, int(len(all_links) * delete_rate))
    to_delete = random.sample(all_links, min(num_delete, len(all_links)))

    deleted_by_file: dict[str, set[str]] = {}
    for src, tgt in to_delete:
        deleted_by_file.setdefault(src, set()).add(tgt)

    total_deleted = 0
    for stem, targets in deleted_by_file.items():
        for f in tmp.iterdir():
            if f.stem == stem and f.is_file():
                total_deleted += delete_links_from_file(f, targets)
                break

    print(f"Prepared degraded wiki: {tmp}")
    print(f"  Total links in ground truth: {len(all_links)}")
    print(f"  Deleted: {total_deleted} ({delete_rate*100:.0f}%)")
    print(f"  Remaining: {len(all_links) - total_deleted}")
    return tmp


# --- Step 2: 跑精化闭环 ---

def run_refinement_loop(
    wiki_dir: Path,
    api_key: str,
    base_url: str | None = None,
    model: str = "deepseek-chat",
) -> dict:
    """对 wiki_dir 跑完整的 importer → refine 闭环。

    TODO: 实现真实的 LLM 调用（judge → abduct → refine）。
    当前为骨架——需要填充 agent loop 的每步逻辑。

    Returns: 精化结果，包含：
      - refined_graph: 精化后的 graph.json dict
      - refinement_actions: LLM 生成的修复动作列表
      - trace: 完整的 interaction_trace
    """
    # TODO: 实现
    # 1. wiki_importer.import_wiki(wiki_dir, ...)
    # 2. 对每个 query → wiki_retrieval.retrieve(...)
    # 3. LLM judge（调用 REAFINER_JUDGEMENT_USER prompt）
    # 4. 如果 answerable=False → LLM abduct → LLM refine
    # 5. agent_graph.apply_actions_to_graphify(...)
    raise NotImplementedError(
        "精化闭环需要真实 LLM API 调用。请参考 POC 的 test_llm_wiki.py 或 "
        "feasibilityReport.md §3.3 的真实 DeepSeek 验证方式实现。"
    )


# --- Step 3: 计算召回率 ---

def compute_recovery_metrics(
    deleted_links: set[tuple[str, str]],
    refinement_actions: list[str],
) -> dict:
    """计算精化恢复了多少被删除的链接。

    Args:
        deleted_links: {(source_stem, target_label), ...} 被删除的链接
        refinement_actions: ["insert_edge('A','links_to','B')", ...]

    Returns:
        {recovered, total_deleted, recovery_rate, false_positives, precision}
    """
    recovered = set()
    false_positives = set()

    # TODO: 解析 refinement_actions 中的 insert_edge，匹配 deleted_links
    for action in refinement_actions:
        # 解析 "insert_edge('A', 'links_to', 'B')"
        pass

    total_deleted = len(deleted_links)
    recovery_rate = len(recovered) / total_deleted if total_deleted else 0
    precision = (
        len(recovered) / (len(recovered) + len(false_positives))
        if (recovered or false_positives)
        else 0
    )

    return {
        "recovered": len(recovered),
        "total_deleted": total_deleted,
        "recovery_rate": recovery_rate,
        "false_positives": len(false_positives),
        "precision": precision,
    }


def main():
    parser = argparse.ArgumentParser(description="Refinement recall benchmark")
    parser.add_argument("--wiki-dir", type=Path, required=True, help="Wiki 目录")
    parser.add_argument("--delete-rate", type=float, default=0.2, help="链接删除比例 (0-1)")
    parser.add_argument("--api-key", type=str, help="LLM API key（或设环境变量）")
    parser.add_argument("--base-url", type=str, help="LLM API base URL")
    parser.add_argument("--model", type=str, default="deepseek-chat")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--output", type=Path, help="保存结果 JSON")
    args = parser.parse_args()

    random.seed(args.seed)
    wiki_dir = args.wiki_dir.resolve()

    if not wiki_dir.is_dir():
        print(f"Wiki directory not found: {wiki_dir}", file=sys.stderr)
        sys.exit(1)

    # Step 1: 记录 ground truth
    print("=" * 60)
    print("Step 1: Recording ground truth links...")
    truth = record_ground_truth(wiki_dir)
    total_links = sum(len(v) for v in truth.values())
    print(f"  Pages with links: {len(truth)}")
    print(f"  Total links: {total_links}")

    # Step 2: 准备不完整 KG
    print("\n" + "=" * 60)
    print("Step 2: Preparing degraded wiki...")
    degraded_dir = prepare_degraded_wiki(wiki_dir, truth, args.delete_rate)

    # Step 3: 跑精化
    print("\n" + "=" * 60)
    print("Step 3: Running refinement loop...")
    print("  (需要真实 LLM API——当前为骨架)")
    api_key = args.api_key or __import__("os").environ.get("OPENAI_API_KEY")
    if not api_key:
        print("  ⚠️  未提供 API key，无法调用 LLM。请通过 --api-key 或环境变量提供。")
        print("  eval 脚本骨架已就绪，实现 LLM 调用逻辑后即可运行。")
        sys.exit(0)

    try:
        result = run_refinement_loop(
            degraded_dir,
            api_key=api_key,
            base_url=args.base_url,
            model=args.model,
        )
    except NotImplementedError as e:
        print(f"\n  {e}")
        sys.exit(0)

    # Step 4: 计算指标
    # TODO

    # Cleanup
    import shutil
    shutil.rmtree(degraded_dir)


if __name__ == "__main__":
    main()
