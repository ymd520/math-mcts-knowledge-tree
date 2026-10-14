import Lean

open Lean Elab Command Meta

-- This file is an end-to-end *core Lean* extraction smoke test.
-- A pinned mathlib environment is needed to export real Mathlib constants.
theorem mathMctsProofReferenceDemo (n : Nat) : n + 0 = n := Nat.add_zero n

#eval liftTermElabM do
  let env ← getEnv
  let name := ``mathMctsProofReferenceDemo
  let some info := env.find? name
    | throwError "Could not read elaborated demonstration theorem"
  let typeRefs := info.type.getUsedConstants.map (·.toString)
  let proofRefs := match info.value? true with
    | some v => v.getUsedConstants.map (·.toString)
    | none => #[]
  let pretty ← ppExpr info.type
  let payload := Json.mkObj [
    ("declaration", toJson name.toString),
    ("type_expression", toJson pretty.pretty),
    ("type_references", toJson typeRefs),
    ("proof_references", toJson proofRefs),
    ("evidence", toJson "read_from_lean_environment")
  ]
  IO.println payload.compress
