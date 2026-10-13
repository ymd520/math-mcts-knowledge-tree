"""循环深度碰撞: 多轮 MCTS 知识碰撞, 挖掘新颖的跨领域概念对.

第 1 轮: 全局碰撞, 找出高分跨域对.
第 2..N 轮: 把上一轮的新颖对合成为"复合概念"(仅内存中, 不写入知识库),
以复合概念为 seed 再做碰撞, 寻找二阶、三阶交叉.

输出是启发式候选假设(按碰撞分排序), 不是证明、不是新定理.
碰撞分构成: curated 笔记 +2.0 / 跨领域 +0.5 / 双核心 +0.3 /
难度接近 / 共享标签. 详见 math_mcts/search.py::collision_score.

用法: python examples/deep_collide.py [--rounds 3] [--topk 12] [--iterations 3000]
结果存 examples/deep_collide_report.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts import KnowledgeTree, collide_concepts  # noqa: E402
from math_mcts.knowledge import Concept  # noqa: E402


def make_composite(a: Concept, b: Concept, round_no: int, idx: int) -> Concept:
    """把一对碰撞概念合成为复合概念(内存对象, 不入库)."""
    tags = sorted(set(a.tags) | set(b.tags))
    depth = max(getattr(a, "_dc_depth", 0), getattr(b, "_dc_depth", 0)) + 1
    comp = Concept(
        id=f"DC{round_no}_{idx}",
        domain_cn="跨域合成",
        domain_en="CrossSynth",
        branch_cn=f"{a.branch_cn}×{b.branch_cn}",
        topic_cn=f"{a.topic_cn}×{b.topic_cn}",
        cn=f"{a.cn} × {b.cn}",
        en=f"{a.en} x {b.en}",
        definition=f"交叉视角: {a.definition} —— {b.definition}",
        level=min(5, max(1, round((a.level + b.level) / 2))),
        prereq=[a.id, b.id],
        tags=tags,
        kind="思路",
        example=f"由 {a.cn}({a.id}) 与 {b.cn}({b.id}) 碰撞合成的{depth}阶假设",
    )
    comp._dc_depth = depth
    return comp


def pair_key(aid: str, bid: str) -> frozenset:
    return frozenset((aid, bid))


def deep_collide(tree: KnowledgeTree, rounds: int = 3, top_k: int = 12,
                 iterations: int = 3000, seeds_per_round: int = 5,
                 seed_topk: int = 5):
    seen: set[frozenset] = set()
    # curated 已有对不算"新"
    for col in tree.collisions:
        seen.add(pair_key(col["a"], col["b"]))
    report = {"rounds": [], "novel_pairs": []}
    work_tree = tree
    composites: list[Concept] = []

    for r in range(1, rounds + 1):
        t0 = time.time()
        round_pairs = []
        if r == 1:
            results = collide_concepts(work_tree, top_k=top_k,
                                       iterations=iterations)
            for a, b, score, note in results:
                round_pairs.append((a, b, score, note))
        else:
            for comp in composites[:seeds_per_round]:
                results = collide_concepts(work_tree, seed=comp.id,
                                           top_k=seed_topk,
                                           iterations=iterations // 2)
                for a, b, score, note in results:
                    round_pairs.append((a, b, score, note))
        # 去重 + 挑新颖
        novel = []
        for a, b, score, note in round_pairs:
            k = pair_key(a.id, b.id)
            if k in seen:
                continue
            seen.add(k)
            novel.append({"a_id": a.id, "a_cn": a.cn,
                          "a_domain": a.domain_cn,
                          "b_id": b.id, "b_cn": b.cn,
                          "b_domain": b.domain_cn,
                          "score": score, "curated_note": note,
                          "round": r})
        novel.sort(key=lambda x: x["score"], reverse=True)
        report["rounds"].append({
            "round": r, "elapsed_s": round(time.time() - t0, 2),
            "pairs_total": len(round_pairs), "novel": len(novel),
        })
        report["novel_pairs"].extend(novel)
        print(f"[round {r}] {time.time()-t0:.1f}s, pairs={len(round_pairs)}, "
              f"novel={len(novel)}", flush=True)

        # 为下一轮合成复合概念: 允许复合概念继续参与(形成二阶/三阶假设),
        # 但深度不超过 2, 且不做复合×复合(避免语义空转).
        composites = []
        if r < rounds:
            by_id = work_tree.by_id
            new_concepts = list(work_tree.concepts)
            made = 0
            for p in novel:
                if made >= seeds_per_round:
                    break
                a, b = by_id[p["a_id"]], by_id[p["b_id"]]
                da, db = getattr(a, "_dc_depth", 0), getattr(b, "_dc_depth", 0)
                if da > 0 and db > 0:
                    continue  # 复合×复合跳过
                if max(da, db) >= 2:
                    continue  # 深度封顶
                comp = make_composite(a, b, r + 1, made)
                new_concepts.append(comp)
                composites.append(comp)
                made += 1
            if composites:
                work_tree = KnowledgeTree(new_concepts, work_tree.meta,
                                          work_tree.collisions)
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--topk", type=int, default=12)
    ap.add_argument("--iterations", type=int, default=3000)
    args = ap.parse_args()

    tree = KnowledgeTree.load()
    print(f"loaded curated tree: {len(tree.concepts)} concepts, "
          f"{len(tree.collisions)} curated collisions", flush=True)
    t0 = time.time()
    report = deep_collide(tree, rounds=args.rounds, top_k=args.topk,
                          iterations=args.iterations)
    report["elapsed_s"] = round(time.time() - t0, 2)
    report["config"] = vars(args)
    out = Path(__file__).with_name("deep_collide_report.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"done in {report['elapsed_s']}s, "
          f"novel pairs: {len(report['novel_pairs'])}, report -> {out}")


if __name__ == "__main__":
    main()
