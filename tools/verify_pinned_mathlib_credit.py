"""Proof of source *file* attribution, without claiming theorem discoveries."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.attribution import module_source_path,module_source_url,parse_file_header
from math_mcts.source_registry import SOURCE_COMMIT


def verify_pinned_header(root: Path,module: str) -> dict:
    actual=subprocess.run(["git","-C",str(root),"rev-parse","HEAD"],
                          capture_output=True,text=True,check=True).stdout.strip()
    if actual != SOURCE_COMMIT:
        raise ValueError("Module header requires exact pinned Mathlib source commit")
    relative=module_source_path(module)
    source=(root/relative).resolve()
    if not source.is_relative_to(root.resolve()):
        raise ValueError("Source path escaped root")
    if not source.is_file():
        raise ValueError("Missing requested Mathlib source module")
    header=parse_file_header(source.read_text(encoding="utf-8"))
    return {"source_module":module,"source_commit":SOURCE_COMMIT,
            "source_module_url":module_source_url(module),
            "source_path":relative,"file_header":header,
            "attribution_warning":"Module header authors do not establish who first proved every theorem"}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mathlib-root",type=Path,required=True)
    p.add_argument("--module",required=True)
    p.add_argument("--output",type=Path,default=Path("pinned_mathlib_module_credit.json"))
    a=p.parse_args()
    credit=verify_pinned_header(a.mathlib_root,a.module)
    a.output.write_text(json.dumps(credit,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(credit,ensure_ascii=False))


if __name__=="__main__":
    main()
