"""命令行入口.

    python -m math_mcts path "傅里叶变换"      # 规划学习路径
    python -m math_mcts search "贝叶斯 定理"   # 检索相关概念
    python -m math_mcts show "梯度下降"        # 查看概念卡片
    python -m math_mcts export-path "傅里叶变换" -o plan.md  # 导出学习计划
    python -m math_mcts collide "傅里叶变换"   # 知识碰撞
    python -m math_mcts info                  # 知识库概览
"""
from __future__ import annotations

import argparse

from .knowledge import KnowledgeTree
from .search import (plan_learning_path, search_concepts,
                     export_path_markdown, collide_concepts)


def cmd_path(args):
    tree = KnowledgeTree.load()
    known = [tree.find(k.strip()).id
             for k in args.known.split(",")] if args.known else []
    concepts = plan_learning_path(tree, args.target,
                                  iterations=args.iterations,
                                  known=known)
    print(f"学习目标: {concepts[-1].cn} ({concepts[-1].en})")
    if known:
        print(f"已掌握: {', '.join(tree.get(k).cn for k in known)}")
    print(f"规划路径(共 {len(concepts)} 步):")
    for i, c in enumerate(concepts, 1):
        mark = "★目标" if i == len(concepts) else ""
        print(f"  {i:2d}. [{c.id}] {c.cn} | 难度{c.level}级 | "
              f"{c.path()}{mark}")
        print(f"       定义: {c.definition}")
        if c.formulas:
            print(f"       公式: {' ; '.join(c.formulas)}")


def cmd_search(args):
    tree = KnowledgeTree.load()
    results = search_concepts(tree, args.query, top_k=args.top_k,
                              iterations=args.iterations)
    print(f"检索: {args.query!r} (MCTS 迭代 {args.iterations} 次)")
    for i, (c, visits, mean) in enumerate(results, 1):
        print(f"  {i}. [{c.id}] {c.cn} ({c.en})")
        print(f"     路径: {c.path()} | 访问{visits}次 | 相关度{mean:.2f}")
        print(f"     定义: {c.definition}")


def cmd_show(args):
    tree = KnowledgeTree.load()
    print(tree.find(args.name).card())


def cmd_export_path(args):
    tree = KnowledgeTree.load()
    concepts = plan_learning_path(tree, args.target,
                                  iterations=args.iterations)
    md = export_path_markdown(concepts)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"学习计划已导出: {args.output} (共 {len(concepts)} 步)")


def cmd_collide(args):
    tree = KnowledgeTree.load()
    results = collide_concepts(tree, seed=args.seed, top_k=args.top_k,
                               iterations=args.iterations)
    title = f"围绕「{args.seed}」" if args.seed else "全局"
    print(f"知识碰撞 ({title}, MCTS 迭代 {args.iterations} 次):")
    for i, (a, b, score, note) in enumerate(results, 1):
        print(f"  {i}. {a.cn} × {b.cn}  (碰撞分 {score:.2f})")
        print(f"     {a.domain_cn} / {b.domain_cn}")
        if note:
            print(f"     💡 {note}")
        else:
            print(f"     待探索: {a.definition[:40]}… + {b.definition[:40]}…")


def cmd_info(args):
    tree = KnowledgeTree.load()
    problems = tree.check_integrity()
    print(f"概念总数: {len(tree.concepts)}")
    print("覆盖领域:")
    counts: dict[str, int] = {}
    for c in tree.concepts:
        counts[c.domain_cn] = counts.get(c.domain_cn, 0) + 1
    for name, en in tree.domains():
        print(f"  - {name} ({en}): {counts[name]} 个概念")
    print("完整性自检:", "通过" if not problems else f"{len(problems)} 个问题")
    for p in problems[:10]:
        print("   !", p)


def main():
    ap = argparse.ArgumentParser(prog="math_mcts",
                                 description="数学知识 MCTS 搜索树")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("path", help="规划到目标概念的学习路径")
    p.add_argument("target", help="目标概念(中文名/英文名/id)")
    p.add_argument("--iterations", type=int, default=3000)
    p.add_argument("--known", default="",
                   help="已掌握的概念(逗号分隔), 规划从此之后开始")
    p.set_defaults(func=cmd_path)
    sh = sub.add_parser("show", help="查看概念卡片")
    sh.add_argument("name", help="概念(中文名/英文名/id)")
    sh.set_defaults(func=cmd_show)
    ep = sub.add_parser("export-path", help="导出学习计划为 Markdown")
    ep.add_argument("target", help="目标概念(中文名/英文名/id)")
    ep.add_argument("-o", "--output", default="学习计划.md")
    ep.add_argument("--iterations", type=int, default=3000)
    ep.set_defaults(func=cmd_export_path)
    co = sub.add_parser("collide", help="知识碰撞: 找最值得组合的概念对")
    co.add_argument("seed", nargs="?", default=None,
                    help="围绕哪个概念碰撞(省略=全局最优碰撞对)")
    co.add_argument("--top_k", type=int, default=5)
    co.add_argument("--iterations", type=int, default=3000)
    co.set_defaults(func=cmd_collide)
    s = sub.add_parser("search", help="关键词检索相关概念")
    s.add_argument("query", help="检索关键词")
    s.add_argument("--top_k", type=int, default=5)
    s.add_argument("--iterations", type=int, default=2000)
    s.set_defaults(func=cmd_search)
    i = sub.add_parser("info", help="知识库概览与自检")
    i.set_defaults(func=cmd_info)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
