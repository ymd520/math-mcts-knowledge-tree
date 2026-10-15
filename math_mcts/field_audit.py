"""Reproducible, provenance-aware mathematics field coverage audit.

Five different quantities must NOT be mixed:
* Full imported manifest cards = legacy 234k bulk content, not all inspected here.
* Module-index prefix matches = path PRESENCE, not theorem counts.
* Indexed source declarations = actual candidate rows if an indexed DB is passed.
* Catalog records = edited knowledge cards, with independently separate grade/tag.
* AI proposal cards = independent unverified supplements, never counted as curated.

The 49-field taxonomy is editorial and multi-label; overlapping categories mean
field counts must not be summed as unique source or theorem counts.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sqlite3

from .knowledge import KnowledgeTree, MODULE_INDEX_PATH, IMPORTED_DIR
from .catalog import name_key

TAXONOMY_PATH = Path(__file__).with_name("data") / "field_taxonomy_v1.json"
STATUS_UNGRADED = ("ungraded", "unrated", "provisional")


def load_taxonomy(path: str | Path = TAXONOMY_PATH) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != "math-mcts-field-taxonomy-v1":
        raise ValueError("unsupported field taxonomy version")
    fields = data.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValueError("field taxonomy cannot be empty")
    ids = set()
    for row in fields:
        if (not isinstance(row, dict) or
            set(row) != {"id","domain","field","module_prefixes",
                         "curated_title_terms","review_priority"} or
            not all(isinstance(row[k],str) and row[k]
                    for k in ("id","domain","field")) or
            row["id"] in ids or
            row["review_priority"] not in {"P0","P1","P2"}):
            raise ValueError("invalid/duplicate field taxonomy row")
        ids.add(row["id"])
        for key in ("module_prefixes", "curated_title_terms"):
            seq = row[key]
            if not isinstance(seq,list) or not seq or any(
                not isinstance(x,str) or not x.strip() for x in seq):
                raise ValueError("invalid taxonomy mapping list")
        if any(not prefix.startswith("Mathlib.") for prefix in row["module_prefixes"]):
            raise ValueError("mathlib module prefix must be explicit")
    return fields


def _matching_modules(path, prefixes):
    return any(path == p or path.startswith(p + ".") for p in prefixes)


def _catalog_matches(row, field):
    if row.domain_cn != field["domain"]:
        return False
    # A lexical preview, NOT a mathematical classifier. Only match entire
    # terms or phrases (as provided in curated_title_terms) inside card text.
    # Exact branch equality is also a legitimate editorial tag match.
    if row.branch_cn == field["field"]:
        return True
    blob = name_key(" ".join((row.cn, row.en, row.branch_cn, row.topic_cn)))
    return any(name_key(term) in blob for term in field["curated_title_terms"])


def _indexed_module_counts(path: str | Path) -> tuple[dict,dict]:
    """Read one group-by over indexed source records, not 49 independent scans."""
    with sqlite3.connect(str(path)) as db:
        table_names = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "classified_knowledge" not in table_names:
            raise ValueError("index requires classified_knowledge, not raw text only")
        records = db.execute(
            "SELECT source_module,source_tier,registration_status,"
            "importance_status,difficulty_level,COUNT(*) "
            "FROM classified_knowledge GROUP BY 1,2,3,4,5").fetchall()
    by_module: dict[str,Counter] = {}
    diagnostics=Counter()
    for module,tier,status,importance,level,count in records:
        if not module:
            diagnostics["unknown_module_source_records"] += count
            continue
        c=by_module.setdefault(module,Counter())
        c["records"]+=count
        c["tier:"+tier]+=count
        c["registration:"+status]+=count
        c["importance:"+importance]+=count
        c["grade_assigned" if level is not None else "grade_unassigned"]+=count
        if tier=="unreviewed_import":
            c["imported_grade_unassigned" if level is None else "imported_grade_assigned"]+=count
        diagnostics["indexed_source_records"]+=count
    return by_module,dict(diagnostics)


def audit_fields(*, tree: KnowledgeTree | None = None,
                 module_index: dict | None = None,
                 indexed_db: str | Path | None = None,
                 taxonomy_path: str | Path = TAXONOMY_PATH,
                 source_manifest: dict | None = None,
                 ai_candidates: list[dict] | None = None) -> dict:
    fields=load_taxonomy(taxonomy_path)
    if tree is None:
        tree=KnowledgeTree.load()
    if module_index is None:
        module_index=json.loads(MODULE_INDEX_PATH.read_text(encoding="utf-8"))
    if source_manifest is None:
        source_manifest=json.loads((IMPORTED_DIR / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(module_index,dict):
        raise ValueError("module index must be a mapping")
    module_paths=tuple(sorted(module_index))
    indexed, diagnostics=(_indexed_module_counts(indexed_db)
                          if indexed_db is not None else ({},{}))
    ai_candidates=ai_candidates or []
    result=[]
    for row in fields:
        paths=[name for name in module_paths
               if _matching_modules(name,row["module_prefixes"])]
        authored=[item for item in tree.concepts if _catalog_matches(item,row)]
        levels=Counter()
        tagged=0
        status=Counter()
        for item in authored:
            label=(item.level_status or "").lower()
            if any(marker in label for marker in STATUS_UNGRADED):
                levels["unrated_or_provisional"]+=1
            elif type(item.level) is int and 1<=item.level<=5:
                levels[str(item.level)]+=1
            else:
                levels["unknown"]+=1
            tagged+=bool({"核心","重要"} & set(item.tags))
            status[item.verification_status or "unspecified"]+=1
        evidence=Counter()
        # Count only records actually present in an indexed source DB.
        # The module-index path count alone is *not* evidence of a theorem.
        for module,metrics in indexed.items():
            if _matching_modules(module,row["module_prefixes"]):
                evidence.update(metrics)
        proposals=sum(bool(
            item.get("domain")==row["domain"] and item.get("branch")==row["field"])
            for item in ai_candidates)
        # Priorities are editorial *audit work* ordering, not importance of
        # any upstream theorem; sparse coverage never proves absence.
        if not paths and not authored:
            gap="no_matching_module_paths_or_catalog_title_evidence"
        elif not authored:
            gap="catalog_title_gap_while_upstream_modules_may_exist"
        elif len(authored)<3:
            gap="few_lexically_matching_catalog_cards"
        else:
            gap="audit_depth_and_rule_reusability"
        result.append({
            "id":row["id"],"domain":row["domain"],"field":row["field"],
            "review_priority":row["review_priority"],
            "module_prefixes":row["module_prefixes"],
            "module_index_paths_matched":len(paths),
            "catalog_lexical_matches":len(authored),
            "catalog_important_tagged":tagged,
            "catalog_level_counts_not_certified":dict(sorted(levels.items())),
            "catalog_verification_statuses":dict(sorted(status.items())),
            "ai_unreviewed_field_proposals":proposals,
            "indexed_imported_records":evidence.get("tier:unreviewed_import") if indexed_db is not None else None,
            "indexed_curated_records":evidence.get("tier:curated") if indexed_db is not None else None,
            "indexed_source_registered":evidence.get("registration:source_statement_registered") if indexed_db is not None else None,
            "indexed_imported_importance_unrated":evidence.get("importance:importance_unrated") if indexed_db is not None else None,
            "indexed_imported_grade_unassigned":evidence.get("imported_grade_unassigned",0) if indexed_db is not None else None,
            "independent_theorem_proof_count":None,
            "coverage_work_label":gap,
        })
    return {
        "schema":"math-mcts-field-audit-v1",
        "taxonomy_fields":len(result),
        "domain_count":len({f["domain"] for f in result}),
        "total_catalog_rows":len(tree.concepts),
        "catalog_inventory_by_domain":tree.inventory()["domains"],
        "source_manifest_imported_cards":source_manifest.get("imported_cards"),
        "source_index_module_prefix_paths":len(module_paths),
        "indexed_subset_evidence":diagnostics,
        "ai_proposals_total_separate":len(ai_candidates),
        "claims":{"mathlab_module_prefixes_are_theorem_counts":False,
                  "lexical_catalog_match_is_verified_classification":False,
                  "editorial_important_tag_is_kernel_proof":False,
                  "imported_placeholder_level_is_real_difficulty":False,
                  "multilabel_field_totals_can_be_summed_to_unique_count":False},
        "fields":result,
    }


def choose_audit_queue(report: dict, *, max_fields: int = 20) -> list[dict]:
    if type(max_fields) is not int or max_fields < 1:
        raise ValueError("invalid audit queue limit")
    rank={"P0":0,"P1":1,"P2":2}
    return [{
        "id":r["id"],"field":r["field"],"domain":r["domain"],
        "reason":r["coverage_work_label"],
        "priority_is_editorial_not_mathematical":True,
        "catalog_lexical_matches":r["catalog_lexical_matches"],
        "module_index_paths_matched":r["module_index_paths_matched"],
        "indexed_imported_records":r["indexed_imported_records"]
    } for r in sorted(
        report["fields"],
        key=lambda x:(rank[x["review_priority"]],
                      x["catalog_lexical_matches"],
                      x["module_index_paths_matched"],x["id"]))[:max_fields]]
