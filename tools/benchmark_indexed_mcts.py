"""Run data-backed searches and verify actual knowledge use, without proof claims."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from math_mcts.indexed_mcts import research_with_knowledge

p = argparse.ArgumentParser()
p.add_argument('--db', type=Path, required=True)
p.add_argument('--iterations', type=int, default=120)
p.add_argument('--depth', type=int, default=8)
p.add_argument('--output', type=Path, required=True)
args = p.parse_args()
reports = []
for query in ('compact topology continuous', 'convex optimization inequality',
              'prime polynomial divisibility'):
    report = research_with_knowledge(query, db_path=args.db,
                                    iterations=args.iterations, depth=args.depth,
                                    seed=23, top_k=3)
    assert report['coverage']['complete_imported_index']
    assert report['coverage']['indexed_imported'] == report['coverage']['manifest_imported']
    assert report['usage']['selected_by_source_tier'].get('unreviewed_import', 0) > 0
    assert report['usage']['retrieval_calls'] > 1
    assert any(event['depth'] > 0 for event in report['retrieval_trace'])
    ids = {card['id'] for card in report['knowledge_records']}
    assert ids and any(card['source_tier'] == 'unreviewed_import'
                       for card in report['knowledge_records'])
    assert all(set(path['knowledge_ids']) <= ids for path in report['paths'])
    assert not report['proof_verified']
    reports.append(report)
    print(json.dumps({'query': query, 'coverage': report['coverage'],
                      'usage': report['usage'], 'elapsed_seconds': report['elapsed_seconds']},
                      ensure_ascii=False), flush=True)
args.output.write_text(json.dumps({'runs': reports}, ensure_ascii=False, indent=2) + '\n')
