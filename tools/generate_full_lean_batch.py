"""Generate one exact-source Lean extraction script from the full-corpus manifest.

Only manifests produced from the immutable source registry are accepted; this
tool does not claim any theorem was elaborated or discovered.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from math_mcts.source_registry import SOURCE_COMMIT
from math_mcts.full_lean_plan import partition_batches


def generate_batch_script(plan_path: Path, batch_id: str, target: Path) -> dict:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan["mathlib_commit"] != SOURCE_COMMIT:
        raise ValueError("Plan has a different upstream commit")
    selected = [b for b in plan["batches"] if b["batch_id"] == batch_id]
    if len(selected) != 1:
        raise ValueError("Batch ID must be present exactly once")
    batch = selected[0]
    records = batch["registered_declarations"]
    digest = hashlib.sha256(json.dumps(
        records, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    if digest != batch["batch_sha256"]:
        raise ValueError("Batch source fingerprint is stale")
    module = batch["module"]
    if len(records) > 200 or not records:
        raise ValueError("Invalid batch size")
    lines = [
        f"import {module}",
        "open Lean Elab Command Meta",
        "",
        "#eval liftTermElabM do",
        "  let env ← getEnv",
    ]
    for request in records:
        name = request["declaration"]
        sid = request["source_id"]
        sha = request["source_statement_sha256"]
        # Construct a Lean.Name AST, not untrusted Lean source identifiers:
        # this also supports Unicode names not accepted by ASCII-only syntax.
        lean_name = "Lean.Name.anonymous"
        for part in name.split("."):
            lean_name = f"Lean.Name.str ({lean_name}) {json.dumps(part, ensure_ascii=False)}"
        lines.extend([
            f"  let requested : Lean.Name := {lean_name}",
            "  match env.find? requested with",
            "  | none =>",
            "      let missing := Json.mkObj [",
            f'        ("missing_declaration", toJson {json.dumps(name)}),',
            f'        ("source_id", toJson {json.dumps(sid)})',
            "      ]",
            "      IO.println missing.compress",
            "  | some info =>",
            "      let typeRefs := info.type.getUsedConstants.map (·.toString)",
            "      let proofRefs : Array String := match info.value? true with",
            "        | some v => v.getUsedConstants.map (fun n => n.toString)",
            "        | none => #[]",
            "      let formatted ← ppExpr info.type",
            "      let payload := Json.mkObj [",
            f'        ("source_id", toJson {json.dumps(sid)}),',
            '        ("declaration", toJson requested.toString),',
            f'        ("module", toJson {json.dumps(module)}),',
            f'        ("mathlib_commit", toJson {json.dumps(SOURCE_COMMIT)}),',
            f'        ("source_statement_sha256", toJson {json.dumps(sha)}),',
            '        ("type_expression", toJson formatted.pretty),',
            '        ("type_references", toJson typeRefs),',
            '        ("proof_references", toJson proofRefs),',
            '        ("lean_version", toJson "pinned-mathlib-toolchain")',
            "      ]",
            "      IO.println payload.compress",
        ])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"batch_id":batch_id, "selected":len(records),
            "module":module, "module_path":batch["module_path"],
            "batch_sha256":digest, "execution_status":"script_only_not_extracted"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--batch-id", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(generate_batch_script(args.plan,args.batch_id,args.output),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
