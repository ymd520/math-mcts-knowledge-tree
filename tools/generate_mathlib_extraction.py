"""Generate a Lean script to extract selected registered Mathlib declarations.

This script itself does not certify Lean execution. Run generated Lean code
under the *source commit's own pinned toolchain*, then import JSONL using
math_mcts.lean_reference_index. Name resolution may fail for imported aliases;
such cases remain unmatched and are explicitly logged, never guessed.
"""
from __future__ import annotations
import argparse
import json
import re
import sqlite3
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.source_registry import SOURCE_COMMIT

# Mathlib has many unicode/quoted names; skip unsupported syntax rather than
# constructing potentially invalid or misleading Lean AST identifiers.
_IDENT=re.compile(r"^[A-Za-z_][A-Za-z_0-9'.]*(?:\.[A-Za-z_0-9']+)*$")


def generate(db_path: Path, script_path: Path, *, limit: int=20,
             module_prefix: str | None=None) -> dict:
    if limit<1 or limit>200:
        raise ValueError("Use 1..200 requests in a controlled sample")
    requests=[]
    unsupported=0
    with sqlite3.connect(db_path) as cx:
        cursor=cx.execute("""SELECT d.record, sr.source_sha256
              FROM source_registry sr JOIN documents d ON d.id=sr.id
              ORDER BY sr.id""")
        for raw,sha in cursor:
            row=json.loads(raw)
            module=row.get("module","")
            if module_prefix and not module.startswith(module_prefix):
                continue
            name=row.get("en","")
            if not _IDENT.fullmatch(name):
                unsupported+=1
                continue
            requests.append((row["id"],name,module,sha))
            if len(requests)>=limit:
                break
    if not requests:
        raise ValueError("No admissible source declarations for the sample")

    # Import only source modules actually requested. Importing the umbrella
    # Mathlib module would require a full multi-thousand-file cache, whereas
    # targeted imports admit a significantly smaller dependency closure.
    modules=sorted(set(module for _,_,module,_ in requests))
    pieces=[
        *(f"import {module}" for module in modules),
        "open Lean Elab Command Meta",
        "",
        "-- Auto-generated request list. This is NOT a proof.",
        "#eval liftTermElabM do",
        "  let env ← getEnv",
    ]
    for source_id,name,module,sha in requests:
        # Antiquoted syntax identifier produces the exact Lean Name requested;
        # never assume a source display name has a matching environment entry.
        pieces += [
            f"  -- {source_id}: {module}",
            f"  let requested := ``{name}",
            "  match env.find? requested with",
            "  | none =>",
            "      let missing := Json.mkObj [",
            f'        ("missing_declaration", toJson {json.dumps(name)}),',
            f'        ("source_id", toJson {json.dumps(source_id)})',
            "      ]",
            "      IO.println missing.compress",
            "  | some info =>",
            "      let typeRefs := info.type.getUsedConstants.map (·.toString)",
            "      let proofRefs : Array String := match info.value? true with",
            "        | some v => v.getUsedConstants.map (fun n => n.toString)",
            "        | none => #[]",
            "      let formatted ← ppExpr info.type",
            "      let payload := Json.mkObj [",
            f'        ("source_id", toJson {json.dumps(source_id)}),',
            '        ("declaration", toJson requested.toString),',
            f'        ("module", toJson {json.dumps(module)}),',
            f'        ("mathlib_commit", toJson {json.dumps(SOURCE_COMMIT)}),',
            f'        ("source_statement_sha256", toJson {json.dumps(sha)}),',
            '        ("type_expression", toJson formatted.pretty),',
            '        ("type_references", toJson typeRefs),',
            '        ("proof_references", toJson proofRefs),',
            '        ("lean_version", toJson "mathlib pinned lean-toolchain")',
            "      ]",
            "      IO.println payload.compress",
        ]
    script_path.parent.mkdir(parents=True,exist_ok=True)
    script_path.write_text("\n".join(pieces)+"\n",encoding="utf-8")
    return {"selected":len(requests),"ignored_unsupported_names":unsupported,
            "selected_source_modules":modules,
            "pinned_mathlib_commit":SOURCE_COMMIT,
            "warning":"Only actual successful Lean environment output can be imported"}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--output",type=Path,default=Path("lean/ExtractSelected.lean"))
    p.add_argument("--limit",type=int,default=20)
    p.add_argument("--module-prefix")
    a=p.parse_args()
    print(json.dumps(generate(a.db,a.output,limit=a.limit,
                             module_prefix=a.module_prefix),ensure_ascii=False))


if __name__=="__main__":
    main()
