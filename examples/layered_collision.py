"""Reproducible synthetic all-to-all dependency fixture, NOT novel mathematics.

Layer l has width conclusions. Each depends on all width facts in layer l-1.
All final-layer facts are explicit goals, so every derived fact is goal-relevant.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def make_problem(width=20, layers=20):
    if width < 20 or layers < 20:
        raise ValueError("Require width >=20, layers >=20")
    def atom(l, j):
        return {"predicate": f"fact_{l}_{j}", "args": []}
    rules = []
    for l in range(1, layers + 1):
        previous = [atom(l - 1, j) for j in range(width)]
        for j in range(width):
            rules.append({"id": f"layer_{l:03}_rule_{j:03}", "premises": previous,
                          "conclusion": atom(l, j), "variables": {},
                          "source": "synthetic benchmark: stipulated implications, not mathematical theorems",
                          "status": "reviewed"})
    return {"signatures": {f"fact_{l}_{j}": [] for l in range(layers + 1) for j in range(width)},
            "objects": {}, "assumptions": [atom(0, j) for j in range(width)],
            "goals": [atom(layers, j) for j in range(width)], "rules": rules,
            "layer_config": {"min_knowledge": width, "min_layers": layers,
                             "max_layers": layers, "batch_width": width}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=20)
    ap.add_argument("--layers", type=int, default=20)
    ap.add_argument("-o", "--output", default="layered_problem.json")
    args = ap.parse_args()
    Path(args.output).write_text(json.dumps(make_problem(args.width, args.layers), indent=2) + "\n")
    print(f"Synthetic fixture written: {args.layers} layers x {args.width} inputs/outputs")
