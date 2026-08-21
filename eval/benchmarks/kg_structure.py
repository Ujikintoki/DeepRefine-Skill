#!/usr/bin/env python3
"""图结构指标评估：精化前后 KG 拓扑指标对比。

不依赖真实 LLM，纯 networkx 计算。对 graph.json 跑一组拓扑指标，
输出可量化的"图质量"变化。

用法:
    python eval/benchmarks/kg_structure.py --before graph_before.json --after graph_after.json
    python eval/benchmarks/kg_structure.py --graph graph.json  # 单图分析
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

# TODO: networkx is not in the project's dependencies.
# Install via: pip install networkx
try:
    import networkx as nx
except ImportError:
    print("networkx not installed. Run: pip install networkx", file=sys.stderr)
    sys.exit(1)


def load_graph(graph_path: Path) -> dict:
    return json.loads(graph_path.read_text(encoding="utf-8"))


def graph_to_nx(graph_data: dict) -> nx.DiGraph:
    """Convert graph.json dict → networkx DiGraph."""
    G = nx.DiGraph()
    for node in graph_data.get("nodes", []):
        G.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    links = graph_data.get("links") or graph_data.get("edges") or []
    for link in links:
        G.add_edge(
            link["source"],
            link["target"],
            relation=link.get("relation", "links_to"),
        )
    return G


def compute_metrics(G: nx.DiGraph, max_hop: int = 3) -> dict:
    """Compute a standard set of graph structure metrics."""
    metrics: dict = {}
    num_nodes = G.number_of_nodes()
    num_edges = G.number_of_edges()

    # Node-level
    in_degrees = dict(G.in_degree())
    out_degrees = dict(G.out_degree())
    metrics["num_nodes"] = num_nodes
    metrics["num_edges"] = num_edges
    metrics["avg_in_degree"] = float(np.mean(list(in_degrees.values()))) if num_nodes else 0
    metrics["avg_out_degree"] = float(np.mean(list(out_degrees.values()))) if num_nodes else 0
    metrics["max_in_degree"] = max(in_degrees.values()) if num_nodes else 0
    metrics["max_out_degree"] = max(out_degrees.values()) if num_nodes else 0

    # Edge-level
    if num_nodes > 1:
        metrics["edge_density"] = num_edges / (num_nodes * (num_nodes - 1))
    else:
        metrics["edge_density"] = 0.0

    reciprocal = sum(1 for u, v in G.edges() if G.has_edge(v, u))
    metrics["reciprocal_edge_fraction"] = reciprocal / num_edges if num_edges else 0.0

    # Path-level
    if nx.is_weakly_connected(G) and num_nodes > 1:
        try:
            sp_lengths = dict(nx.all_pairs_shortest_path_length(G, cutoff=max_hop))
            lengths = []
            for d in sp_lengths.values():
                lengths.extend(list(d.values()))
            metrics["avg_shortest_path_length"] = float(np.mean(lengths)) if lengths else None
        except Exception:
            metrics["avg_shortest_path_length"] = None
    else:
        metrics["avg_shortest_path_length"] = None

    # Graph-level
    metrics["num_weakly_connected_components"] = nx.number_weakly_connected_components(G)
    metrics["num_strongly_connected_components"] = nx.number_strongly_connected_components(G)

    # Relation diversity
    relations = [data.get("relation", "") for _, _, data in G.edges(data=True)]
    rel_freq = np.array(list(Counter(relations).values()))
    if len(rel_freq) > 0:
        probs = rel_freq / rel_freq.sum()
        metrics["relation_entropy"] = float(-np.sum(probs * np.log(probs + 1e-9)))
    else:
        metrics["relation_entropy"] = 0.0
    metrics["unique_relation_types"] = len(set(relations))

    return metrics


def print_metrics(metrics: dict, label: str = "") -> None:
    header = f" [{label}]" if label else ""
    print(f"\n{'='*50}")
    print(f"Graph Structure Metrics{header}")
    print(f"{'='*50}")
    for k, v in metrics.items():
        if v is None:
            print(f"  {k:40s}  N/A (disconnected)")
        else:
            print(f"  {k:40s}  {v:.4f}" if isinstance(v, float) else f"  {k:40s}  {v}")


def print_comparison(before: dict, after: dict) -> None:
    print(f"\n{'='*60}")
    print("  Before → After 对比")
    print(f"{'='*60}")
    comparable_keys = [
        k for k in before
        if k in after and isinstance(before[k], (int, float)) and before[k] is not None
    ]
    for k in comparable_keys:
        delta = after[k] - before[k]
        direction = "↑" if delta > 0 else "↓" if delta < 0 else "→"
        print(f"  {k:40s}  {before[k]:.4f} → {after[k]:.4f}  ({direction} {delta:+.4f})")


def main():
    parser = argparse.ArgumentParser(description="KG structure benchmark")
    parser.add_argument("--graph", type=Path, help="Single graph.json to analyze")
    parser.add_argument("--before", type=Path, help="graph.json before refinement")
    parser.add_argument("--after", type=Path, help="graph.json after refinement")
    parser.add_argument("--max-hop", type=int, default=3, help="Max hop for shortest path (default: 3)")
    parser.add_argument("--output", type=Path, help="Save metrics as JSON")
    args = parser.parse_args()

    if args.graph:
        g = load_graph(args.graph)
        G = graph_to_nx(g)
        metrics = compute_metrics(G, max_hop=args.max_hop)
        print_metrics(metrics, label=args.graph.name)
        if args.output:
            args.output.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))

    elif args.before and args.after:
        g_before = load_graph(args.before)
        g_after = load_graph(args.after)
        G_before = graph_to_nx(g_before)
        G_after = graph_to_nx(g_after)

        m_before = compute_metrics(G_before, max_hop=args.max_hop)
        m_after = compute_metrics(G_after, max_hop=args.max_hop)

        print_metrics(m_before, label="BEFORE")
        print_metrics(m_after, label="AFTER")
        print_comparison(m_before, m_after)

        if args.output:
            args.output.write_text(json.dumps({
                "before": m_before,
                "after": m_after,
            }, indent=2, ensure_ascii=False))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
