import Lean
open Lean Elab Command Meta

-- Extract the actual elaborated Expr binder telescope, without claiming
-- successful proof composition. Binder-domain expressions may contain bvars.
partial def mctsForallBinders : Expr → Array Json
  | .forallE nm dom rest bi =>
    #[Json.mkObj [
        ("name", toJson nm.toString),
        ("domain_ast", toJson (reprStr dom)),
        ("domain_constants", toJson (dom.getUsedConstants.map (·.toString))),
        ("binder_info", toJson (reprStr bi))
      ]] ++ mctsForallBinders rest
  | _ => #[]

partial def mctsForallBody : Expr → Expr
  | .forallE _ _ rest _ => mctsForallBody rest
  | e => e

theorem mctsStructureDemo (P : Nat → Prop) (n : Nat) (hn : P n) : P n := hn

#eval liftTermElabM do
  let some info := (← getEnv).find? ``mctsStructureDemo
    | throwError "missing structure theorem"
  let binders := mctsForallBinders info.type
  let body := mctsForallBody info.type
  let result := Json.mkObj [
      ("binder_count", toJson binders.size),
      ("binders", toJson binders),
      ("conclusion_ast", toJson (reprStr body)),
      ("conclusion_constants", toJson (body.getUsedConstants.map (·.toString))),
      ("source", toJson "actual_elaborated_lean_expr")
    ]
  IO.println result.compress
