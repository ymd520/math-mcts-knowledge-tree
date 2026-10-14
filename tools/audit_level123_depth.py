"""Editorial status and traceable source audit for Level 1–3 study expansion."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.knowledge import KnowledgeTree
from math_mcts.deep_core import SEED_PATH


def audit():
    tree=KnowledgeTree.load()
    base=KnowledgeTree.load(include_supplements=False)
    deep=[c for c in tree.concepts if c.id.startswith("D123_")]
    counts=Counter((c.domain_cn,c.level) for c in deep)
    cross=[{"from":dep,"to":c.id,"from_domain":tree.get(dep).domain_cn,
            "to_domain":c.domain_cn}
           for c in deep for dep in c.prereq if tree.get(dep).domain_cn!=c.domain_cn]
    bad=[c.id for c in deep if not(
        c.assumptions and c.conclusion and c.proof_idea and
        c.misuse_counterexample and c.source_url and c.source_locator and
        c.statement_sha256 and c.reference_relation=="topic_reference_not_statement_certification")]
    if bad:
        raise ValueError("Knowledge lacks proof hints / negative cases / source metadata: "+
                         repr(bad))
    if tree.check_integrity():
        raise ValueError("Catalog integrity broken")
    expected=sum(1 for line in SEED_PATH.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.strip().startswith(("#","@")))
    if len(deep)!=expected:
        raise ValueError(f"Expected {expected} source-seed annotated cards, got {len(deep)}")
    return {
        "base_catalog_count":len(base.concepts),
        "supplemented_catalog_count":len(tree.concepts),
        "deep_level123_added":len(deep),
        "seed_knowledge_rows":expected,
        "domain_level_counts":[{"domain":d,"level":l,"count":n}
                             for (d,l),n in sorted(counts.items())],
        "cross_domain_explicit_prerequisites":len(cross),
        "cross_domain_examples":cross[:18],
        "source_relation":"topic_reference_only_not_exact_theorem_proof",
        "reviewed_by_independent_mathematician":0,
        "claimed_new_original_theorems":0,
        "lean_kernel_verified_new_cards":0,
        "curricular_importance_status":"provisional_editorial_candidates",
        "legacy_catalog_unchanged":True,
    }


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,default=Path("level123_deep_audit.json"))
    args=p.parse_args()
    result=audit()
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2))
