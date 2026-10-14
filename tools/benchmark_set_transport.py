"""20×20 parallel finite-set membership reasoning benchmark with failure cases."""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from examples.set_membership_20x20 import run_set_transport


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,default=Path("set_transport_20x20.json"))
    p.add_argument("--seeds",type=int,nargs="+",default=[3,7,11])
    p.add_argument("--iterations",type=int,default=3)
    a=p.parse_args()
    outputs=[]
    for seed in a.seeds:
        started=time.perf_counter()
        trial=run_set_transport(iterations=a.iterations,seed=seed)
        elapsed=1000*(time.perf_counter()-started)
        outputs.append({
            "seed":seed,"elapsed_ms":round(elapsed,3),
            "status":trial["status"],"metrics":trial["metrics"],
            "candidate_truncated":trial["candidate_truncated"],
            "search_complete":trial["search_complete"],
            "verified_only_relative_to_explicit_set_rule":True,
        })
    failed=run_set_transport(iterations=a.iterations,
                             omit_subset_at=9,seed=a.seeds[0])
    report={
        "task":"twenty_parallel_memberships_across_twenty_inclusions",
        "mathematically_valid_schema":"x∈A and A⊆B imply x∈B",
        "trials":outputs,
        "missing_inclusion_rejected":failed["certificate"] is None,
        "scope":"constructed elementary mathematics test; not a research theorem",
    }
    a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"results":[{"seed":x["seed"],"status":x["status"],
                "elapsed_ms":x["elapsed_ms"]} for x in outputs],
                "missing_inclusion_rejected":report["missing_inclusion_rejected"]},
                ensure_ascii=False))
    if any(x["status"]!="derived_relative_to_rules" for x in outputs):
        raise SystemExit(1)
    if not report["missing_inclusion_rejected"]:
        raise SystemExit(2)


if __name__=="__main__":
    main()
