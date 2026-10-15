"""Solve or independently verify explicitly selected logic problems.

Usage:
  python tools/solve_logic.py input.json --output result.json
  python tools/solve_logic.py input.json --verify result.json

This CLI never upgrades candidate rules to reviewed status.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from math_mcts.logic_router import solve_problem, verify_problem


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("problem", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--max-states", type=int, default=4000)
    parser.add_argument("--max-term-nodes", type=int, default=100)
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--max-cases", type=int, default=2000)
    parser.add_argument("--max-proof-nodes", type=int, default=5000)
    parser.add_argument("--max-guard-attempts", type=int, default=300)
    args = parser.parse_args()
    problem = json.loads(args.problem.read_text(encoding="utf-8"))
    if args.verify:
        report = json.loads(args.verify.read_text(encoding="utf-8"))
        ok = verify_problem(problem, report)
        print(json.dumps({"certificate_replayed": ok,
                          "logic": problem.get("logic")}, ensure_ascii=False))
        return 0 if ok else 1
    outcome = solve_problem(problem, max_steps=args.max_steps,
                            max_states=args.max_states,
                            max_term_nodes=args.max_term_nodes,
                            iterations=args.iterations,
                            max_cases=args.max_cases, max_nodes=args.max_proof_nodes,
                            max_guard_attempts=args.max_guard_attempts)
    rendered = json.dumps(outcome, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
