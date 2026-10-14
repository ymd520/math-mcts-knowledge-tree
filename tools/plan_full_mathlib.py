"""Create and verify an exhaustive plan for every registered Mathlib theorem."""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.lean_fullscale import plan_full_corpus, verify_manifest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--db",type=Path,help="Registered 100k-source index")
    parser.add_argument("--output",type=Path,default=Path("full_mathlib_plan"))
    parser.add_argument("--shards",type=int,default=64)
    parser.add_argument("--batch-size",type=int,default=80)
    parser.add_argument("--verify-only",action="store_true")
    args=parser.parse_args()
    result=(verify_manifest(args.output) if args.verify_only
            else plan_full_corpus(args.db,args.output,shards=args.shards,
                                  batch_size=args.batch_size))
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=="__main__":
    main()
