"""Execute selected full-plan batches with bounded resources and explicit receipts.

A receipt says only what a concrete Lean process actually returned. Running
scripts in a pinned Lean checkout is mandatory; importing arbitrary JSON
does not establish verified formal mathematics.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.source_registry import SOURCE_COMMIT
from math_mcts.full_lean_plan import partition_batches
from tools.generate_full_lean_batch import generate_batch_script

PINNED_TOOLCHAIN="leanprover/lean4:v4.35.0-rc4"


def _pinned_checkout(repo: Path):
    sha=subprocess.run(["git","-C",str(repo),"rev-parse","HEAD"],
       capture_output=True,text=True,check=True).stdout.strip()
    if sha != SOURCE_COMMIT:
        raise ValueError("Full extraction forbidden on a different mathlib revision")
    if (repo/"lean-toolchain").read_text().strip()!=PINNED_TOOLCHAIN:
        raise ValueError("Wrong Mathlib Lean toolchain")


def run_worker(plan_path: Path,mathlib_root: Path,out: Path, *,
               worker: int,workers: int,max_seconds: int=3600,
               max_batches: int=0) -> dict:
    if max_seconds<=0 or max_batches<0:
        raise ValueError("Invalid bounded execution limits")
    _pinned_checkout(mathlib_root)
    plan=json.loads(plan_path.read_text(encoding="utf-8"))
    if plan["mathlib_commit"]!=SOURCE_COMMIT:
        raise ValueError("Full-plan commit mismatch")
    tasks=partition_batches(plan,worker=worker,workers=workers)
    output=out/("worker-%02d" % worker)
    output.mkdir(parents=True,exist_ok=True)
    done=0
    started=time.monotonic()
    prepared=set()
    summaries=[]
    for batch in tasks:
        if max_batches and done>=max_batches:
            break
        if time.monotonic()-started>=max_seconds:
            break
        bid=batch["batch_id"]
        module=batch["module"]
        receipt={"batch_id":bid, "batch_sha256":batch["batch_sha256"],
                 "module":module,"source_commit":SOURCE_COMMIT,
                 "expected_ids":[x["source_id"] for x in batch["registered_declarations"]],
                 "status":"not_executed", "exported_ids":[],
                 "missing_ids":[], "unresolved_reason":None}
        try:
            if module not in prepared:
                setup=subprocess.run(
                    ["bash",str(Path(__file__).with_name("bootstrap_pinned_mathlib.sh")),
                     batch["module_path"]],
                    cwd=mathlib_root,text=True,capture_output=True,timeout=min(800,max_seconds))
                (output/(bid+"-prepare.log")).write_text(
                    (setup.stdout+"\n"+setup.stderr)[-100000:],encoding="utf-8")
                if setup.returncode:
                    receipt["status"]="cache_or_module_build_failed"
                    receipt["unresolved_reason"]="module environment unavailable"
                    raise RuntimeError("Pinned module cache/source compilation failed")
                prepared.add(module)
            script=mathlib_root/("FullBatch"+bid+".lean")
            generate_batch_script(plan_path,bid,script)
            proc=subprocess.run(["lake","env","lean",script.name],
                cwd=mathlib_root,text=True,capture_output=True,timeout=240)
            (output/(bid+"-lean.log")).write_text(
                (proc.stdout+"\n"+proc.stderr)[-100000:],encoding="utf-8")
            if proc.returncode:
                receipt["status"]="lean_compilation_failed"
                receipt["unresolved_reason"]="Lean returned nonzero status"
            else:
                values=[]
                missing=[]
                for line in proc.stdout.splitlines():
                    if not line.startswith("{"):
                        continue
                    o=json.loads(line)
                    if "source_statement_sha256" in o:
                        values.append(o)
                    elif "missing_declaration" in o:
                        missing.append(o["source_id"])
                expected=set(receipt["expected_ids"])
                found=[v["source_id"] for v in values]
                if len(found)!=len(set(found)) or (set(found)|set(missing))!=expected or (set(found)&set(missing)):
                    receipt["status"]="incomplete_or_duplicate_lean_output"
                    receipt["unresolved_reason"]="Lean output does not match exact requested IDs"
                else:
                    receipt["status"]="executed"
                    receipt["exported_ids"]=found
                    receipt["missing_ids"]=missing
                    dest=output/(bid+".jsonl")
                    dest.write_text("".join(json.dumps(v,ensure_ascii=False)+"\n"
                                            for v in values),encoding="utf-8")
                    receipt["export_sha256"]=hashlib.sha256(dest.read_bytes()).hexdigest()
        except (subprocess.TimeoutExpired,RuntimeError,ValueError,KeyError) as exc:
            if receipt["status"]=="not_executed":
                receipt["status"]="worker_error"
                receipt["unresolved_reason"]=str(exc)[:200]
        finally:
            (output/(bid+".receipt.json")).write_text(
                json.dumps(receipt,sort_keys=True,ensure_ascii=False,indent=2)+"\n")
            summaries.append(receipt)
            done+=1
    summary={"worker":worker,"workers":workers,"planned_batches":len(tasks),
             "attempted_batches":done,"not_attempted_batches":len(tasks)-done,
             "executed_batches":sum(x["status"]=="executed" for x in summaries),
             "successful_declarations":sum(len(x["exported_ids"]) for x in summaries),
             "missing_declarations":sum(len(x["missing_ids"]) for x in summaries),
             "elapsed_seconds":round(time.monotonic()-started,1),
             "status":"partial" if done<len(tasks) or
                       any(x["status"]!="executed" for x in summaries) else "complete"}
    (output/"worker_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    return summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--mathlib-root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--worker",type=int,required=True)
    p.add_argument("--workers",type=int,required=True)
    p.add_argument("--max-seconds",type=int,default=3600)
    p.add_argument("--max-batches",type=int,default=0)
    args=p.parse_args()
    print(json.dumps(run_worker(args.plan,args.mathlib_root,args.out,
        worker=args.worker,workers=args.workers,
        max_seconds=args.max_seconds,max_batches=args.max_batches)))


if __name__=="__main__":
    main()
