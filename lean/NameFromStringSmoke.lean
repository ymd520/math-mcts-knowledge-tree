import Lean
open Lean Elab Command Meta

theorem nameFromStringDemo : True := True.intro
theorem «数学定理» : True := True.intro

#eval liftTermElabM do
  let env ← getEnv
  let name := ("nameFromStringDemo".splitOn ".").foldl
    (fun nm part => Lean.Name.str nm part) Lean.Name.anonymous
  if (env.find? name).isNone then
    throwError "Name.str folding could not resolve an elaborated theorem"
  let unicodeName := ("数学定理".splitOn ".").foldl
    (fun nm part => Lean.Name.str nm part) Lean.Name.anonymous
  if (env.find? unicodeName).isNone then
    throwError "Constructed Unicode declaration could not be resolved"
  let result := Json.mkObj [
    ("resolved", toJson true),
    ("unicode_resolved", toJson true),
    ("declaration", toJson name.toString),
    ("method", toJson "Lean.Name.str-fold")
  ]
  IO.println result.compress
