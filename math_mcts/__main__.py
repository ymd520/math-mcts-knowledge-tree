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
import json
from dataclasses import asdict
from pathlib import Path

from .knowledge import KnowledgeTree
from .search import (plan_learning_path, search_concepts,
                     export_path_markdown, collide_concepts)
from .reasoning import load_reasoning_problem, load_certificate, derive, verify_certificate
from .layered import (load_layered_problem, load_layer_certificate, derive_layers,
                      replay_layers, report_json)


def cmd_layers(args):
    book, assumptions, goals, cfg = load_layered_problem(
        json.loads(Path(args.problem).read_text(encoding="utf-8")))
    result = derive_layers(book, assumptions, goals, config=cfg,
                           iterations=args.iterations, seed=args.seed)
    if args.output:
        Path(args.output).write_text(report_json(result) + "\n", encoding="utf-8")
    # Full certificate goes to file; terminal receives concise actual metrics.
    print(report_json({k: v for k, v in result.items() if k != "certificate"}))


def cmd_verify_layers(args):
    book, assumptions, goals, cfg = load_layered_problem(
        json.loads(Path(args.problem).read_text(encoding="utf-8")))
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    try:
        metrics = replay_layers(book, load_layer_certificate(report["certificate"]),
                                assumptions, goals, cfg)
    except (KeyError, ValueError, TypeError, IndexError):
        metrics = None
    print(report_json({"valid_relative_to_rules": metrics is not None, "metrics": metrics}))
    if metrics is None:
        raise SystemExit(1)


def cmd_verify(args):
    payload = json.loads(Path(args.problem).read_text(encoding="utf-8"))
    if getattr(args, "catalog_mapped", False):
        from .semantic import load_catalog_reasoning_problem
        book, assumptions, goal = load_catalog_reasoning_problem(
            payload, KnowledgeTree.load())
    else:
        book, assumptions, goal = load_reasoning_problem(payload)
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    try:
        valid = verify_certificate(book, load_certificate(report["certificate"]), assumptions, goal)
    except (KeyError, TypeError, ValueError):
        valid = False
    print(json.dumps({"valid_relative_to_rules": valid}))
    if not valid:
        raise SystemExit(1)


def cmd_derive(args):
    data = json.loads(Path(args.problem).read_text(encoding="utf-8"))
    if getattr(args, "catalog_mapped", False):
        from .semantic import load_catalog_reasoning_problem
        book, assumptions, goal = load_catalog_reasoning_problem(
            data, KnowledgeTree.load())
    else:
        book, assumptions, goal = load_reasoning_problem(data)
    result = derive(book, assumptions, goal, iterations=args.iterations,
                    max_steps=args.max_steps, seed=args.seed,
                    max_rounds=args.max_rounds, max_edges=args.max_edges)
    def json_default(value):
        if isinstance(value, frozenset):
            return [asdict(a) for a in sorted(value)]
        raise TypeError(type(value).__name__)
    report = json.dumps(asdict(result), default=json_default, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(report + "\n", encoding="utf-8")
    print(report)


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
    tree = apply_catalog_scope(tree, args)
    results = search_concepts(tree, args.query, top_k=args.top_k,
                              iterations=args.iterations)
    print(f"检索: {args.query!r} (全量精确评分排序; 不进行 MCTS 迭代)")
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
    if not (args.curated_only or args.levels or args.important):
        # Ordinary research now uses the complete imported corpus. The older
        # in-memory pair API remains an explicit curated/scoped operation.
        from .indexed_mcts import research_with_knowledge
        report = research_with_knowledge(
            args.seed or '', db_path=args.db, iterations=args.iterations,
            depth=2, top_k=args.top_k, seed=args.random_seed, domain=args.domain)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print('Explicit scope: curated catalog (imported difficulty is unrated).')
    tree = KnowledgeTree.load()
    tree = apply_catalog_scope(tree, args)
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


def cmd_research(args):
    from .indexed_mcts import research_with_knowledge
    report = research_with_knowledge(
        args.objective, db_path=args.db, iterations=args.iterations,
        depth=args.depth, retrieval_width=args.retrieval_width,
        exploration_width=args.exploration_width, seed=args.seed,
        top_k=args.top_k, domain=args.domain)
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
        report = {key: value for key, value in report.items()
                  if key not in {'retrieval_trace', 'knowledge_records'}}
        report['full_report'] = str(args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def cmd_search_index(args):
    from .fast_index import fast_search
    results = fast_search(args.db, args.query, top_k=args.top_k,
                          tier=args.tier, registered_only=args.registered_only)
    print(json.dumps([{"id": item["id"], "name": item.get("cn") or item.get("en"),
                       "module": item.get("module"), "tier": item["index_tier"],
                       "level": item["indexed_level"],
                       "lexical_score": item["lexical_score"]}
                      for item in results], ensure_ascii=False, indent=2))


def cmd_semantic_graph(args):
    from .semantic_graph import build_semantic_graph,SemanticGraph
    payload=json.loads(Path(args.problem).read_text(encoding="utf-8"))
    if args.catalog_mapped:
        from .semantic import load_catalog_reasoning_problem
        book, _, goal=load_catalog_reasoning_problem(payload,KnowledgeTree.load())
    else:
        book, _, goal=load_reasoning_problem(payload)
    result=build_semantic_graph(book, args.output)
    result["backward_relevant_rules"]=SemanticGraph(
        args.output,book=book).backward_relevant_rules(book,goal.predicate)
    print(json.dumps(result,ensure_ascii=False,indent=2))


def cmd_compare_provers(args):
    from .search_eval import benchmark_suite,mathematical_task_fixtures
    report=benchmark_suite(mathematical_task_fixtures(),
                           iterations=args.iterations,max_steps=args.max_steps,
                           beam_width=args.beam_width,seed=args.seed)
    output=json.dumps(report,ensure_ascii=False,indent=2)
    if args.output:
        Path(args.output).write_text(output+"\n",encoding="utf-8")
    print(output)


def cmd_semantic_links(args):
    from .semantic_links import find_composable_rules
    payload = json.loads(Path(args.problem).read_text(encoding="utf-8"))
    if args.catalog_mapped:
        from .semantic import load_catalog_reasoning_problem
        book, _, _ = load_catalog_reasoning_problem(payload, KnowledgeTree.load())
    else:
        book, _, _ = load_reasoning_problem(payload)
    results = find_composable_rules(book, limit=args.limit,
                                    goal_predicate=args.predicate)
    print(json.dumps(results, ensure_ascii=False, indent=2))


def cmd_show_registered(args):
    from .source_registry import get_registered_statement
    record = get_registered_statement(args.db, args.id)
    if record is None:
        raise SystemExit(f"Not registered or not found: {args.id}")
    print(json.dumps(record, indent=2, ensure_ascii=False))


def cmd_knowledge_search(args):
    from .knowledge_bank import KnowledgeBank
    bank = KnowledgeBank(args.db)
    items = bank.search(args.query, domain=args.domain, kind=args.kind,
                        source_tier=args.tier, top_k=args.top_k)
    print(json.dumps(items, ensure_ascii=False, indent=2))


def cmd_knowledge_browse(args):
    from .knowledge_bank import KnowledgeBank
    bank = KnowledgeBank(args.db)
    items = bank.browse(domain=args.domain, kind=args.kind, source_tier=args.tier,
                        after_id=args.after_id, limit=args.limit)
    print(json.dumps(items, ensure_ascii=False, indent=2))


def cmd_review_leads(args):
    from .review_quality import review_queue
    rows = review_queue(args.db, mode=args.mode, limit=args.limit,
                        offset=args.offset)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_knowledge_show(args):
    from .knowledge_bank import KnowledgeBank
    print(json.dumps(KnowledgeBank(args.db).get(args.id),
                     ensure_ascii=False, indent=2))


def cmd_scale_status(args):
    from .scale_plan import expansion_status
    from .fast_index import index_stats
    imports = int(index_stats(args.db)["metadata"]["unreviewed_candidate_count"]) if args.db else 0
    print(json.dumps(expansion_status(KnowledgeTree.load(),
                                      unreviewed_candidates=imports),
                     ensure_ascii=False, indent=2))


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
    print("等级/重要性统计:")
    print(json.dumps(tree.inventory(), ensure_ascii=False, indent=2))


def apply_catalog_scope(tree, args):
    levels = [int(v) for v in args.levels.split(",")] if args.levels else None
    domains = [args.domain] if args.domain else None
    if levels is not None or args.important or domains:
        return tree.select(levels=levels, important_only=args.important, domains=domains)
    return tree


def add_catalog_scope(parser):
    parser.add_argument("--levels", help="逗号分隔的难度等级，例如1,2,3,4")
    parser.add_argument("--important", action="store_true", help="仅核心或重要知识")
    parser.add_argument("--domain", help="仅指定中文领域")


def main():
    ap = argparse.ArgumentParser(prog="math_mcts",
                                 description="数学知识 MCTS 搜索树")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lr = sub.add_parser("derive-layers", help="每层至少20条知识参与、至少20层的同步推导")
    lr.add_argument("problem")
    lr.add_argument("--iterations", type=int, default=50)
    lr.add_argument("--seed", type=int, default=7)
    lr.add_argument("-o", "--output")
    lr.set_defaults(func=cmd_layers)
    lv = sub.add_parser("verify-layers", help="重放分层证书并核验每层宽度与目标实际深度")
    lv.add_argument("problem")
    lv.add_argument("report")
    lv.set_defaults(func=cmd_verify_layers)
    dr = sub.add_parser("derive", help="多前提多层推导（相对于显式审核规则）")
    dr.add_argument("problem", help="带对象类型、前提、规则及目标的 JSON")
    dr.add_argument("--catalog-mapped", action="store_true", help="Require hash-bound reviewed catalog mappings")
    dr.add_argument("--iterations", type=int, default=1000)
    dr.add_argument("--max-steps", type=int, default=50)
    dr.add_argument("--max-rounds", type=int, default=100)
    dr.add_argument("--max-edges", type=int, default=10000)
    dr.add_argument("--seed", type=int, default=7)
    dr.add_argument("-o", "--output")
    dr.set_defaults(func=cmd_derive)
    vr = sub.add_parser("verify-derivation", help="重放 JSON 推导证书，检查规则版本和前提")
    vr.add_argument("problem")
    vr.add_argument("report")
    vr.add_argument("--catalog-mapped", action="store_true", help="Require hash-bound reviewed catalog mappings")
    vr.set_defaults(func=cmd_verify)
    p = sub.add_parser("path", help="按先修依赖拓扑顺序规划学习路径")
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
    add_catalog_scope(co)
    co.add_argument("seed", nargs="?", default=None,
                    help="围绕哪个概念碰撞(省略=全局最优碰撞对)")
    co.add_argument("--top_k", type=int, default=5)
    co.add_argument("--iterations", type=int, default=3000)
    co.add_argument("--db", type=Path, help="完整语料索引；省略则自动构建/复用全量缓存")
    co.add_argument("--curated-only", action="store_true", help="显式仅用精选库的旧配对接口")
    co.add_argument("--random-seed", type=int, default=7)
    co.set_defaults(func=cmd_collide)
    kr = sub.add_parser("research", help="全量知识库驱动的动态多层MCTS；输出研究线索及实际调用日志")
    kr.add_argument("objective", nargs="?", default="")
    kr.add_argument("--db", type=Path, help="须完整覆盖导入语料；省略则自动管理全量缓存")
    kr.add_argument("--iterations", type=int, default=1000)
    kr.add_argument("--depth", type=int, default=20)
    kr.add_argument("--retrieval-width", type=int, default=24)
    kr.add_argument("--exploration-width", type=int, default=8)
    kr.add_argument("--seed", type=int, default=7)
    kr.add_argument("--top-k", type=int, default=5)
    kr.add_argument("--domain")
    kr.add_argument("-o", "--output", type=Path)
    kr.set_defaults(func=cmd_research)
    s = sub.add_parser("search", help="全量精确评分检索相关概念")
    add_catalog_scope(s)
    s.add_argument("query", help="检索关键词")
    s.add_argument("--top_k", type=int, default=5)
    s.add_argument("--iterations", type=int, default=2000)
    s.set_defaults(func=cmd_search)
    si = sub.add_parser("search-index", help="用FTS5索引快速检索大型数学声明库")
    si.add_argument("query")
    si.add_argument("--db", type=Path, required=True)
    si.add_argument("--top-k", type=int, default=10)
    si.add_argument("--tier", choices=["curated", "unreviewed_import"])
    si.add_argument("--registered-only", action="store_true",
                    help="Only source statements passing source-hash registration")
    si.set_defaults(func=cmd_search_index)
    sg = sub.add_parser("semantic-graph", help="从已审核类型化规则建立可校验的邻接索引")
    sg.add_argument("problem")
    sg.add_argument("--catalog-mapped", action="store_true")
    sg.add_argument("--output", type=Path, default=Path("semantic_rules.sqlite"))
    sg.set_defaults(func=cmd_semantic_graph)
    pc = sub.add_parser("compare-provers", help="整除/集合等任务上对照BFS、束搜索与MCTS")
    pc.add_argument("--iterations", type=int, default=200)
    pc.add_argument("--max-steps", type=int, default=16)
    pc.add_argument("--beam-width", type=int, default=12)
    pc.add_argument("--seed", type=int, default=7)
    pc.add_argument("-o", "--output", type=Path)
    pc.set_defaults(func=cmd_compare_provers)
    sl = sub.add_parser("semantic-links", help="类型化规则连接候选；不等于数学证明")
    sl.add_argument("problem")
    sl.add_argument("--catalog-mapped", action="store_true")
    sl.add_argument("--predicate")
    sl.add_argument("--limit", type=int, default=100)
    sl.set_defaults(func=cmd_semantic_links)
    reg = sub.add_parser("show-registered", help="显示已经通过来源指纹核对的数学声明")
    reg.add_argument("id", help="Source concept ID")
    reg.add_argument("--db", type=Path, required=True)
    reg.set_defaults(func=cmd_show_registered)
    ks = sub.add_parser("knowledge-search",
                        help="在分类知识层快速搜索（数学知识与重要性等级分离）")
    ks.add_argument("query")
    ks.add_argument("--db", type=Path, required=True)
    ks.add_argument("--domain", help="中文数学领域")
    ks.add_argument("--kind")
    ks.add_argument("--tier", choices=["curated", "unreviewed_import"])
    ks.add_argument("--top-k", type=int, default=10)
    ks.set_defaults(func=cmd_knowledge_search)
    kb = sub.add_parser("knowledge-browse", help="按领域和类型游标浏览已分类知识")
    kb.add_argument("--db", type=Path, required=True)
    kb.add_argument("--domain")
    kb.add_argument("--kind")
    kb.add_argument("--tier", choices=["curated", "unreviewed_import"])
    kb.add_argument("--after-id", default="")
    kb.add_argument("--limit", type=int, default=50)
    kb.set_defaults(func=cmd_knowledge_browse)
    kl = sub.add_parser("knowledge-show", help="按 ID 查看分类后的数学知识")
    kl.add_argument("id")
    kl.add_argument("--db", type=Path, required=True)
    kl.set_defaults(func=cmd_knowledge_show)
    rv = sub.add_parser("knowledge-review", help="来源与重复疑点审查队列；不代表正式重要性评级")
    rv.add_argument("--db", type=Path, required=True)
    rv.add_argument("--mode", choices=["priority", "anomaly", "duplicate"], default="priority")
    rv.add_argument("--limit", type=int, default=20)
    rv.add_argument("--offset", type=int, default=0)
    rv.set_defaults(func=cmd_review_leads)
    ps = sub.add_parser("scale-status", help="Level1–4十万重要知识目标与实际缺口")
    ps.add_argument("--db", type=Path)
    ps.set_defaults(func=cmd_scale_status)
    i = sub.add_parser("info", help="知识库概览与自检")
    i.set_defaults(func=cmd_info)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()


