"""Small full-index parameter screen; not a replacement for paired MCTS runs."""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from math_mcts.fast_index import build_index
from math_mcts.indexed_mcts import IndexedCorpus, _tokens
# The rejected strategy is archived for reproducibility, not a runtime backend.
import importlib.util
_spec = importlib.util.spec_from_file_location('rejected_sparse',
    Path(__file__).resolve().parents[1] / 'benchmarks/experiments/sparse_retrieval_rejected.py')
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
ExactFTSRetriever = _module.ExactFTSRetriever


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--queries', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    db = args.output / 'full.sqlite'
    start = perf_counter()
    built = build_index(db)
    build_seconds = perf_counter() - start
    queries = json.loads(args.queries.read_text())
    corpus = IndexedCorpus(db)
    try:
        expected = []
        start = perf_counter()
        for item in queries:
            expected.append(corpus.retriever.full_rank(_tokens(item['query'])[:24], item['limit']))
        baseline_seconds = perf_counter() - start
        results = []
        for sparse_limit, pool_limit in ((128, 1024), (512, 8192), (2048, 32768), (8192, 65536)):
            profiles, elapsed = [], 0.
            retriever = None
            previous_trace = None
            for item, target in zip(queries, expected):
                if item['source_trace'] != previous_trace:
                    if retriever is not None:
                        profiles.append(retriever.profile())
                    retriever = ExactFTSRetriever(corpus.db, sparse_limit=sparse_limit,
                                                 pool_limit=pool_limit)
                    previous_trace = item['source_trace']
                start = perf_counter()
                actual = retriever.search(_tokens(item['query'])[:24], item['limit'])
                elapsed += perf_counter() - start
                if actual != target:
                    raise AssertionError({'query': item, 'sparse_limit': sparse_limit,
                                          'actual': actual, 'expected': target})
            profiles.append(retriever.profile())
            result = {'sparse_limit': sparse_limit, 'pool_limit': pool_limit,
                      'seconds': elapsed, 'exact_queries': len(queries), 'profiles': profiles}
            results.append(result)
            print('TUNING_OPTION=' + json.dumps(result), flush=True)
        summary = {'indexed': built, 'build_seconds': build_seconds,
                   'baseline_seconds': baseline_seconds, 'query_count': len(queries),
                   'options': results,
                   'limits': 'Single-pass parameter screen; full paired MCTS validation still required.'}
        (args.output / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
        print('TUNING_RESULT=' + json.dumps(summary), flush=True)
    finally:
        corpus.close()


if __name__ == '__main__':
    main()
