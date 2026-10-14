import Lean
open Lean Elab Command Meta

theorem mctsDefEqProducer : True := True.intro
theorem mctsDefEqConsumer (h : True) : True := h
theorem mctsDefEqNegative (h : False) : True := False.elim h

#eval liftTermElabM do
  let env ← getEnv
  let some producer := env.find? ``mctsDefEqProducer
    | throwError "missing producer"
  let some consumer := env.find? ``mctsDefEqConsumer
    | throwError "missing consumer"
  let some negative := env.find? ``mctsDefEqNegative
    | throwError "missing negative"
  match consumer.type, negative.type with
  | .forallE _ positive _ _, .forallE _ invalid _ _ =>
    let compatible ← isDefEq producer.type positive
    let notCompatible ← isDefEq producer.type invalid
    let output := Json.mkObj [
      ("actual_lean_meta_defeq", toJson compatible),
      ("different_closed_premise_rejected", toJson (!notCompatible)),
      ("proof_of_remaining_conditions", toJson false)
    ]
    IO.println output.compress
  | _, _ => throwError "Expected explicit closed proposition premises"
