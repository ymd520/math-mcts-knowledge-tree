"""Audit a 49-field mathematics taxonomy; preserve review/verification boundaries.

Sample:
 python tools/audit_fields.py --output field_inventory.json \
     --markdown field_inventory.md \
     --ai-pack examples/field_replenishment_v1.json
 python tools/audit_fields.py --indexed-db math_index.sqlite --output full_inventory.json

The indexed database is optional: when omitted, imported statement counts
are null, never inferred from matching module paths.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from math_mcts.field_audit import audit_fields, choose_audit_queue
from math_mcts.ai_knowledge import validate_pack


def markdown_report(report):
    lines=[
        "# Math-MCTS 数学学科覆盖审计（分支级）", "",
        f"- 分类字段：{report['taxonomy_fields']} 个；一级领域：{report['domain_count']} 个",
        f"- 当前编辑知识卡：{report['total_catalog_rows']} 条",
        f"- 历史导入原始知识卡：{report['source_manifest_imported_cards']} 条（未全部独立核验）",
        f"- 模块路径索引：{report['source_index_module_prefix_paths']} 个（非定理数）",
        f"- AI 补齐候选：{report['ai_proposals_total_separate']} 条（不计入正式知识）",
        "- 分类为多标签、词面代理；一个条目可能匹配多个分支，**不可对分支数量简单相加**",
        "- 所有 independently verified theorem counts 保持未知：未经外部证明审计不得估算", "",
        "| 优先级 | 专业分支 | 路径匹配 | 正式卡片词面命中 | 已索引候选 | AI 补充 |",
        "|---|---|---:|---:|---:|---:|"
    ]
    for f in report["fields"]:
        indexed=f["indexed_imported_records"]
        lines.append(
            f"| {f['review_priority']} | {f['field']} | "
            f"{f['module_index_paths_matched']} | {f['catalog_lexical_matches']} | "
            f"{indexed if indexed is not None else '未查询'} | {f['ai_unreviewed_field_proposals']} |")
    lines += ["", "## 优先审核队列（确定性生成，非学术重要性结论）",""]
    for row in choose_audit_queue(report,max_fields=20):
        lines.append(
            f"- {row['id']} {row['field']}: {row['reason']}；正式卡词面命中 "
            f"{row['catalog_lexical_matches']}，导入模块路径 "
            f"{row['module_index_paths_matched']}")
    return "\n".join(lines)+"\n"


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--indexed-db",type=Path)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--markdown",type=Path)
    p.add_argument("--ai-pack",type=Path,action="append",default=[])
    args=p.parse_args()
    proposals=[]
    for path in args.ai_pack:
        pack=validate_pack(json.loads(path.read_text(encoding="utf-8")))
        proposals.extend(pack["items"])
    report=audit_fields(indexed_db=args.indexed_db,ai_candidates=proposals)
    report["queue"]=choose_audit_queue(report)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True,
                                     ensure_ascii=False)+"\n",encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True,exist_ok=True)
        args.markdown.write_text(markdown_report(report),encoding="utf-8")
    print(json.dumps({
        "fields":report["taxonomy_fields"],
        "domains":report["domain_count"],
        "curated_cards":report["total_catalog_rows"],
        "historical_imported_cards":report["source_manifest_imported_cards"],
        "module_prefix_index":report["source_index_module_prefix_paths"],
        "ai_proposals":report["ai_proposals_total_separate"],
        "actual_imported_counts_available":bool(args.indexed_db),
        "report":str(args.output),
    },ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
