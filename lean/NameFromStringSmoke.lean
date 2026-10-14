import Lean
open Lean Elab Command Meta

theorem nameFromStringDemo : True := True.intro

#eval liftTermElabM do
  let env ← getEnv
  let name := Lean.Name.fromString "nameFromStringDemo"
  if (env.find? name).isNone then
    throwError "Name.fromString could not resolve an elaborated theorem"
  let result := Json.mkObj [
    ("resolved", toJson true),
    ("declaration", toJson name.toString),
    ("method", toJson "Lean.Name.fromString")
  ]
  IO.println result.compress
