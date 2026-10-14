"""Build stable mathlib module-level holdouts for independent search tests."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.lean_holdout import create_module_splits


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--report",type=Path,default=Path("lean_module_holdout.json"))
    a=p.parse_args()
    print(json.dumps(create_module_splits(a.db,a.report),ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
