"""Paired, phase-timed full-corpus retrieval benchmark; never a proof test.

Run this same harness against two pinned source checkouts and shared data.
Each measured research run is a new process (fresh Python/query caches).
Operating-system caches are not flushed. Method timers overlap deliberately.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import subprocess
import sys
from time import perf_counter


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def worker(args):
    sys.path.insert(0, str(args.root.resolve()))
    import math_mcts.indexed_mcts as im
    from math_mcts.literature_bridge import HybridCorpus
    task = json.loads(args.task.read_text())
    phases = defaultdict(float)
    calls = defaultdict(int)

    def instrument(owner, name, key):
        original = getattr(owner, name)
        @wraps(original)
        def wrapped(*a, **kw):
            start = perf_counter()
            try:
                return original(*a, **kw)
            finally:
                phases[key] += perf_counter() - start
                calls[key] += 1
        setattr(owner, name, wrapped)

    instrument(im, 'validate_full_index', 'index_validation')
    instrument(im.IndexedCorpus, '__init__', 'primary_open')
    instrument(HybridCorpus, '__init__', 'external_open')
    instrument(im, 'mcts', 'tree_search')
    for cls, name, key in (
        (im.IndexedCorpus, 'search', 'primary_search_inclusive'),
        (im.IndexedCorpus, 'sample', 'random_sampling_inclusive'),
        (im.IndexedCorpus, '_decode', 'primary_decode_inclusive'),
        (im.IndexedCorpus, 'get', 'primary_get_inclusive'),
        (HybridCorpus, 'search', 'hybrid_search_inclusive'),
        (HybridCorpus, 'get', 'external_or_primary_get_inclusive'),
    ):
        instrument(cls, name, key)
    start = perf_counter()
    report = im.research_with_knowledge(
        task['query'], db_path=args.primary_db,
        external_db_path=args.external_db if task['mode'] == 'hybrid' else None,
        iterations=task['iterations'], depth=task['depth'],
        retrieval_width=task['retrieval_width'], exploration_width=task['exploration_width'],
        seed=task['seed'])
    research_wall = perf_counter() - start
    phase_names = ('index_validation', 'primary_open', 'external_open', 'tree_search')
    exclusive = {k: phases[k] for k in phase_names}
    exclusive['report_and_close'] = research_wall - sum(exclusive.values())
    # Serialize full evidence separately, retaining IDs, source metadata and trace.
    serial_start = perf_counter()
    raw = json.dumps(report, ensure_ascii=False)
    serialization = perf_counter() - serial_start
    write_start = perf_counter()
    args.raw.write_text(raw + '\n', encoding='utf-8')
    disk_write = perf_counter() - write_start
    path_ids = sorted({cid for p in report['paths'] for cid in p['knowledge_ids']})
    out = {
        'task': task, 'research_wall_seconds': research_wall,
        'exclusive_phases_seconds': exclusive,
        'nested_diagnostics_seconds_do_not_sum': dict(phases),
        'method_calls': dict(calls), 'serialization_seconds': serialization,
        'raw_write_seconds': disk_write, 'raw_report_bytes': len(raw.encode()),
        'runtime_timings_seconds': report.get('timings_seconds'),
        'coverage': report['coverage'], 'usage': report['usage'], 'mcts': report['mcts'],
        'path_ids': path_ids,
        'path_sha256': hashlib.sha256(json.dumps(report['paths'], sort_keys=True).encode()).hexdigest(),
        'raw_report': str(args.raw), 'proof_verified': report['proof_verified'],
    }
    args.result.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')


def run(args):
    root = args.current_root.resolve()
    sys.path.insert(0, str(root))
    from math_mcts.fast_index import build_index
    from math_mcts.indexed_mcts import validate_full_index
    from math_mcts.source_adapters import discover_candidates, persist_candidates
    from math_mcts.source_expansion import _connect
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = json.loads(args.config.read_text())
    db = output / 'full.sqlite'
    ext = output / 'external.sqlite'
    overall_start = perf_counter()
    start = perf_counter()
    built = build_index(db)
    build_seconds = perf_counter() - start
    start = perf_counter()
    coverage = validate_full_index(db)
    validation_seconds = perf_counter() - start
    ext.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(ext)
    conn.commit()
    conn.close()
    providers = ('theoremsearch', 's2orc', 'zbmath', 'realmath')
    fetched, prefetch = {}, {}
    start = perf_counter()
    if args.prefetch:
        def discover(source):
            ts = perf_counter()
            try:
                rows = discover_candidates(source, query=config['objectives'][0]['query'],
                                           limit=config.get('external_prefetch_limit', 6))
                return rows, {'status': 'fetched', 'fetch_seconds': perf_counter()-ts}
            except Exception as exc:
                return None, {'status': 'failed', 'error': str(exc),
                              'fetch_seconds': perf_counter()-ts}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(discover, source): source for source in providers}
            for f in as_completed(futures):
                source = futures[f]
                rows, prefetch[source] = f.result()
                if rows is not None:
                    fetched[source] = rows
        for source in providers:
            if source in fetched:
                ts = perf_counter()
                try:
                    prefetch[source]['import'] = persist_candidates(ext, source, fetched[source])
                except Exception as exc:
                    prefetch[source].update(status='cache_error', error=str(exc))
                prefetch[source]['persist_seconds'] = perf_counter() - ts
    prefetch_wall = perf_counter() - start
    with sqlite3.connect(ext) as con:
        source_counts = dict(con.execute('SELECT source,COUNT(*) FROM external_candidates GROUP BY source'))
    inputs = {'config_sha256': sha(args.config), 'primary_db_sha256': sha(db),
              'external_db_sha256': sha(ext)}
    roots = {'before': args.baseline_root.resolve(), 'after': root}
    commits = {k: subprocess.check_output(['git', '-C', str(v), 'rev-parse', 'HEAD'], text=True).strip()
               for k, v in roots.items()}
    runs = []
    # Save after every run, so interrupted experiments retain evidence.
    summary = {'status': 'in_progress', 'case_id': config['case_id'],
               'mathematical_problem': config['mathematical_problem'],
               'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                               'sqlite': sqlite3.sqlite_version},
               'commits': commits, 'inputs': inputs, 'coverage': coverage, 'build_result': built,
               'setup_seconds': {'full_index_build': build_seconds,
                                 'initial_full_validation': validation_seconds,
                                 'parallel_prefetch_and_serial_import': prefetch_wall},
               'prefetch': prefetch, 'external_counts': source_counts, 'runs': runs,
               'limits': ['Knowledge retrieval experiment, not G5C proof.',
                          'Shared database and fixed query/seed/budget; no OS-cache flush.',
                          'Each run is a fresh process; query caches warm only inside a run.',
                          'Nested method timings overlap and must not be summed.',
                          'Hybrid quota fix can change paths; speed alone is not quality.',
                          'Public samples/metadata only; no full external datasets loaded.']}
    def save():
        (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    save()
    for rep in range(args.repetitions):
        for objective in config['objectives']:
            for mode in ('primary', 'hybrid'):
                order = ('before', 'after') if rep % 2 == 0 else ('after', 'before')
                for version in order:
                    label = f"{objective['label']}_{mode}_{version}_{rep}"
                    task = {**objective, 'mode': mode, 'version': version, 'repetition': rep,
                            **{k: config[k] for k in ('depth', 'retrieval_width', 'exploration_width', 'seed')}}
                    task_file, result_file = output / (label+'.task.json'), output / (label+'.result.json')
                    task_file.write_text(json.dumps(task))
                    ts = perf_counter()
                    subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker',
                        '--root', str(roots[version]), '--task', str(task_file),
                        '--primary-db', str(db), '--external-db', str(ext),
                        '--raw', str(output/(label+'.raw.json')), '--result', str(result_file)],
                        check=True, timeout=1200)
                    run = json.loads(result_file.read_text())
                    run['process_wall_seconds'] = perf_counter()-ts
                    runs.append(run)
                    save()
                    print('BENCH_RUN='+json.dumps({k: run[k] for k in (
                        'task', 'exclusive_phases_seconds', 'research_wall_seconds', 'usage')},
                        ensure_ascii=False), flush=True)
    grouped = defaultdict(list)
    for entry in runs:
        t = entry['task']
        grouped[(t['label'], t['mode'], t['version'])].append(entry)
    stats = []
    for (label, mode, version), entries in grouped.items():
        metrics = {key: [e['exclusive_phases_seconds'][key] for e in entries]
                   for key in entries[0]['exclusive_phases_seconds']}
        metrics['research_wall'] = [e['research_wall_seconds'] for e in entries]
        metrics['serialization'] = [e['serialization_seconds'] for e in entries]
        stats.append({'objective': label, 'mode': mode, 'version': version,
                      'repetitions': len(entries),
                      'seconds': {k: {'median': statistics.median(v), 'min': min(v), 'max': max(v)}
                                  for k, v in metrics.items()},
                      'deterministic_paths': len({e['path_sha256'] for e in entries}) == 1})
    summary.update(status='completed', statistics=stats,
                   whole_benchmark_seconds=perf_counter()-overall_start,
                   inputs_unchanged=(sha(db)==inputs['primary_db_sha256'] and
                                     sha(ext)==inputs['external_db_sha256']))
    save()
    print('BENCH_SUMMARY='+json.dumps({k: v for k, v in summary.items() if k != 'runs'},
                                    ensure_ascii=False), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--worker', action='store_true')
    for name in ('root', 'task', 'primary-db', 'external-db', 'raw', 'result',
                 'baseline-root', 'current-root', 'config', 'output'):
        p.add_argument('--'+name, type=Path)
    p.add_argument('--prefetch', action='store_true')
    p.add_argument('--repetitions', type=int, default=3)
    args = p.parse_args()
    if args.repetitions < 1:
        p.error('repetitions must be positive')
    worker(args) if args.worker else run(args)


if __name__ == '__main__':
    main()
