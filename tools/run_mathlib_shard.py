"""Bounded resumable, source-matched Lean extraction shard runner.

This runs pinned Lean for every *runnable* declaration selected in a shard.
It records all missing, failures and unprocessed IDs; no failed extraction is
promoted to verified mathematical knowledge. Python JSON alone is untrusted.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.lean_fullscale import (PINNED_TOOLCHAIN, VALID_NAME,
                                    verify_manifest)
from math_mcts.source_registry import SOURCE_COMMIT


def _one_batch_script(batch: dict) -> str:
    module=batch["module"]
    # Exactly the structure already proven in the 6-theorem pinned Lean job.
    lines=[
        f"import {module}", "open Lean Elab Command Meta",
        "partial def mctsForallBinders : Expr → Array Json",
        "  | .forallE nm dom rest bi =>",
        "    #[Json.mkObj [",
        '        ("name", toJson nm.toString),',
        '        ("domain_ast", toJson (reprStr dom)),',
        '        ("domain_constants", toJson (dom.getUsedConstants.map (·.toString))),',
        '        ("binder_info", toJson (reprStr bi))',
        "      ]] ++ mctsForallBinders rest",
        "  | _ => #[]",
        "partial def mctsForallBody : Expr → Expr",
        "  | .forallE _ _ rest _ => mctsForallBody rest",
        "  | e => e",
        "#eval liftTermElabM do","  let env ← getEnv"]
    for record in batch["records"]:
        name=record["name"]
        if len(name)>1024 or not VALID_NAME.fullmatch(name):
            raise ValueError("Unsupported Lean declaration name")
        lines.extend([
            '  let requested := (' + json.dumps(name,ensure_ascii=False) + '.splitOn ".").foldl', 
            '    (fun nm part => Lean.Name.str nm part) Lean.Name.anonymous',
            "  match env.find? requested with",
            "  | none =>",
            "      let missing := Json.mkObj [",
            f'        ("missing_declaration", toJson {json.dumps(name)}),',
            f'        ("source_id", toJson {json.dumps(record["source_id"])})',
            "      ]",
            "      IO.println missing.compress",
            "  | some info =>",
            "      let typeRefs := info.type.getUsedConstants.map (·.toString)",
            "      let proofRefs := match info.value? true with",
            "        | some v => v.getUsedConstants.map (·.toString)",
            "        | none => #[]",
            "      let formatted ← ppExpr info.type",
            "      let payload := Json.mkObj [",
            f'        ("source_id", toJson {json.dumps(record["source_id"])}),',
            "        (\"declaration\", toJson requested.toString),",
            f'        ("module", toJson {json.dumps(module)}),',
            f'        ("mathlib_commit", toJson {json.dumps(SOURCE_COMMIT)}),',
            f'        ("source_statement_sha256", toJson {json.dumps(record["source_sha256"])}),',
            '        ("type_expression", toJson formatted.pretty),',
            '        ("type_binders", toJson (mctsForallBinders info.type)),',
            '        ("conclusion_ast", toJson (reprStr (mctsForallBody info.type))),',
            '        ("conclusion_constants", toJson ((mctsForallBody info.type).getUsedConstants.map (·.toString))),',
            '        ("type_structure_source", toJson "actual_elaborated_lean_expr"),',
            '        ("type_references", toJson typeRefs),',
            '        ("proof_references", toJson proofRefs),',
            f'        ("lean_version", toJson {json.dumps(PINNED_TOOLCHAIN)})',
            "      ]",
            "      IO.println payload.compress",
        ])
    return "\n".join(lines)+"\n"


def run_shard(plan_root: Path, shard_index: int, *, mathlib_root: Path,
              output_root: Path, dry_run: bool = False,
              max_batches: int | None = None,
              timeout_sec: int = 720,
              cache_timeout_sec: int = 360) -> dict:
    verify_manifest(plan_root)
    manifest=json.loads((plan_root/"manifest.json").read_text())
    if not 0 <= shard_index < manifest["shard_count"]:
        raise ValueError("Unknown shard")
    if max_batches is not None and max_batches < 1:
        raise ValueError("max_batches must be positive")
    piece=json.loads((plan_root/manifest["shards"][shard_index]["file"]).read_text())
    root=mathlib_root.resolve()
    if not dry_run:
        actual=subprocess.run(["git","-C",str(root),"rev-parse","HEAD"],
                              capture_output=True,text=True,check=True).stdout.strip()
        if actual!=SOURCE_COMMIT:
            raise ValueError("Refuse to use Mathlib from wrong commit")
        if (root/"lean-toolchain").read_text().strip()!=PINNED_TOOLCHAIN:
            raise ValueError("Refuse incompatible Lean toolchain")
    out=output_root / f"shard-{shard_index:03d}"
    out.mkdir(parents=True,exist_ok=True)
    status_path=out/"status.jsonl"
    extracted_path=out/"extracted.jsonl"
    journal={}
    if status_path.exists():
        for line in status_path.read_text(encoding="utf-8").splitlines():
            item=json.loads(line)
            if item["source_id"] in journal:
                raise ValueError("Duplicate checkpoint source ID")
            journal[item["source_id"]]=item
    by_id={r["source_id"]:r for batch in piece["batches"] for r in batch["records"]}
    blocked={r["source_id"]:r for r in piece["blocked"]}
    for cid, item in journal.items():
        source=by_id.get(cid)
        if source is None and cid not in blocked:
            raise ValueError("Checkpoint ID missing from current shard")
        if source and item["source_sha256"]!=source["source_sha256"]:
            raise ValueError("Stale checkpoint source fingerprint")
    successes={}
    if extracted_path.exists():
        for line in extracted_path.read_text(encoding="utf-8").splitlines():
            record=json.loads(line)
            cid=record["source_id"]
            if cid in successes:
                raise ValueError("Duplicate extracted theorem in checkpoint")
            if cid not in journal or journal[cid]["status"]!="extracted":
                raise ValueError("Extracted JSON has no successful journal evidence")
            if record["source_statement_sha256"]!=by_id[cid]["source_sha256"]:
                raise ValueError("Tampered extracted fingerprint")
            successes[cid]=record
    if any(item["status"]=="extracted" and cid not in successes
           for cid,item in journal.items()):
        raise ValueError("Missing extracted payload for a successful checkpoint")
    def checkpoint(row):
        cid=row["source_id"]
        if cid in journal:
            raise ValueError("Duplicate terminal source ID")
        with status_path.open("a",encoding="utf-8") as f:
            f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
            f.flush()
        journal[cid]=row

    for record in piece["blocked"]:
        if record["source_id"] not in journal and not dry_run:
            checkpoint({**record, "source_sha256":None,
                        "status":"blocked_before_lean"})
    attempted_batches=0
    prepared_modules={}
    for seq,batch in enumerate(piece["batches"]):
        unprocessed=[r for r in batch["records"] if r["source_id"] not in journal]
        if not unprocessed:
            continue
        if max_batches is not None and attempted_batches >= max_batches:
            break
        attempted_batches+=1
        mod=batch["module"]
        script_content=_one_batch_script({**batch,"records":unprocessed})
        script_path=out / f"lean-batch-{seq:05d}.lean"
        script_path.write_text(script_content,encoding="utf-8")
        if dry_run:
            continue
        module_file=root / (mod.replace(".","/")+".lean")
        if not module_file.is_file():
            prepared_modules[mod]="source_module_missing_at_pinned_commit"
        elif mod not in prepared_modules:
            prepare=subprocess.run(
                ["bash",str(Path(__file__).resolve().parent/"bootstrap_pinned_mathlib.sh"),
                 mod.replace(".","/")+".lean"],
                cwd=root, text=True,capture_output=True,
                timeout=cache_timeout_sec,check=False)
            (out / f"module-cache-{hashlib.sha256(mod.encode()).hexdigest()[:12]}.log").write_text(
                (prepare.stdout+"\n"+prepare.stderr)[-80000:],encoding="utf-8")
            prepared_modules[mod]="ready" if prepare.returncode==0 else "cache_or_build_failed"
        if prepared_modules[mod]!="ready":
            for row in unprocessed:
                checkpoint({"source_id":row["source_id"],"source_sha256":row["source_sha256"],
                            "status":prepared_modules[mod],"module":mod})
            continue
        # Place temporary script into actual Mathlib checkout: lake env will
        # elaborate it against the same pinned Mathlib environment.
        tmp=root/"MctsBatchExtract.lean"
        tmp.write_text(script_content,encoding="utf-8")
        try:
            result=subprocess.run(["lake","env","lean",tmp.name],
                                  cwd=root,text=True,capture_output=True,
                                  timeout=timeout_sec,check=False)
            raw=result.stdout+"\n"+result.stderr
            code=result.returncode
        except subprocess.TimeoutExpired as err:
            raw=str(err)
            code=124
        finally:
            tmp.unlink(missing_ok=True)
        (out/f"lean-output-{seq:05d}.log").write_text(raw[-100000:],encoding="utf-8")
        exports={}
        missing=set()
        if code==0:
            for line in raw.splitlines():
                if not line.startswith("{"):
                    continue
                try:
                    obj=json.loads(line)
                except json.JSONDecodeError:
                    continue
                cid=obj.get("source_id")
                if cid not in {r["source_id"] for r in unprocessed}:
                    continue
                if cid in exports or cid in missing:
                    raise ValueError("Lean extractor emitted duplicate source ID")
                if "source_statement_sha256" in obj:
                    exports[cid]=obj
                elif "missing_declaration" in obj:
                    missing.add(cid)
        for row in unprocessed:
            cid=row["source_id"]
            if cid in exports:
                obj=exports[cid]
                if (obj.get("module")!=mod or
                        obj.get("source_statement_sha256")!=row["source_sha256"] or
                        obj.get("mathlib_commit")!=SOURCE_COMMIT or
                        not isinstance(obj.get("type_expression"),str)):
                    raise ValueError("Lean output does not match exact source request")
                with extracted_path.open("a",encoding="utf-8") as f:
                    f.write(json.dumps(obj,ensure_ascii=False,sort_keys=True)+"\n")
                successes[cid]=obj
                status="extracted"
            elif cid in missing:
                status="not_found_in_lean_environment"
            elif code==124:
                status="lean_timeout"
            else:
                status="lean_error_or_no_output"
            checkpoint({"source_id":cid,"source_sha256":row["source_sha256"],
                        "module":mod,"status":status})
    totals=Counter(r["status"] for r in journal.values())
    expected=manifest["shards"][shard_index]["candidate_count"]+piece["blocked"].__len__()
    summary={"shard":shard_index,"expected":expected,
             "terminal":len(journal),"remaining":expected-len(journal),
             "counts":dict(sorted(totals.items())),
             "extracted":len(successes),
             "mathlib_commit":SOURCE_COMMIT,
             "result_status":"dry_run_only" if dry_run else
                ("all_terminal" if len(journal)==expected else "partial_resume_needed"),
             "warning":"Evidence of actual Lean process belongs to CI logs, not an arbitrary JSON flag"}
    (out/"report.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",
                                    encoding="utf-8")
    return summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--shard",type=int,required=True)
    p.add_argument("--mathlib-root",type=Path,default=Path("mathlib4"))
    p.add_argument("--output",type=Path,default=Path("lean_full_results"))
    p.add_argument("--dry-run",action="store_true")
    p.add_argument("--max-batches",type=int)
    p.add_argument("--timeout-sec",type=int,default=720)
    p.add_argument("--cache-timeout-sec",type=int,default=360)
    a=p.parse_args()
    r=run_shard(a.plan,a.shard,mathlib_root=a.mathlib_root,
                output_root=a.output,dry_run=a.dry_run,
                max_batches=a.max_batches,timeout_sec=a.timeout_sec,
                cache_timeout_sec=a.cache_timeout_sec)
    print(json.dumps(r,ensure_ascii=False))


if __name__=="__main__":
    main()
