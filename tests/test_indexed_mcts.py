"""Adversarial integration checks for full-corpus dynamic knowledge retrieval."""
import random
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import argparse
import contextlib
import io
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.fast_index import build_index
from math_mcts.indexed_mcts import (IndexedCorpus, KnowledgeMCTSProblem,
                                     research_with_knowledge, validate_full_index,
                                     ensure_full_index)


def fixture(root):
    rows = []
    for i in range(36):
        rows.append({'id': f'I{i:03}', 'cn': f'knowledge {i}',
                     'en': 'bridge_keyword' if i == 0 else f'lemma_{i}',
                     'definition': ('origin_word' if i == 0 else
                                    'bridge_keyword consequence' if i == 1 else f'field_{i} topic'),
                     'formal': f'theorem t{i} : synthetic_proposition_{i}',
                     'module': f'Mathlib.{"Analysis" if i % 2 else "Algebra"}.Test',
                     'domain_en': 'Analysis' if i % 2 else 'Algebra',
                     'domain_cn': 'Analysis' if i % 2 else 'Algebra',
                     'level': 5, 'tags': ['待审'], 'verification_status': 'pending',
                     'original_metadata': {'类型': 'upstream_theorem',
                         '陈述SHA256': hashlib.sha256(f'statement_{i}'.encode()).hexdigest()}})
    data = gzip.compress(json.dumps({'concepts': rows}).encode())
    (root / 'cards.json.gz').write_bytes(data)
    (root / 'manifest.json').write_text(json.dumps({'imported_cards': len(rows),
        'expected_cards': len(rows), 'files': [{'shard': 'cards.json.gz',
        'card_count': len(rows), 'shard_sha256': hashlib.sha256(data).hexdigest()}]}))
    return rows


class IndexedMCTSTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rows = fixture(self.root)
        self.path = self.root / 'full.sqlite'
        build_index(self.path, include_curated=False, imported_root=self.root)

    def test_query_cache_reuses_hits_and_misses_with_snapshot_isolation(self):
        corpus = IndexedCorpus(self.path)
        self.addCleanup(corpus.close)
        statements = []
        corpus.db.set_trace_callback(statements.append)
        for query in ('origin_word', 'absent_unique_token'):
            first = [c['id'] for c in corpus.search(query, 4)]
            statements.clear()
            self.assertEqual(first, [c['id'] for c in corpus.search(query, 4)])
            self.assertFalse(any('MATCH' in sql for sql in statements))
        self.assertEqual(corpus.query_cache_hits, 2)
        fresh = IndexedCorpus(self.path)
        self.addCleanup(fresh.close)
        self.assertEqual(fresh.query_cache_hits, 0)
        self.assertEqual(len(fresh._qcache), 0)

    def test_phase_timings_include_report_assembly(self):
        report = research_with_knowledge('origin_word', db_path=self.path,
                    iterations=5, depth=3, imported_root=self.root)
        self.assertTrue(all(t >= 0 for t in report['timings_seconds'].values()))
        self.assertAlmostEqual(sum(report['timings_seconds'].values()),
                               report['elapsed_seconds'])

    def test_default_index_admits_entire_imported_corpus(self):
        meta = validate_full_index(self.path, imported_root=self.root)
        self.assertEqual(meta['actual_imported'], len(self.rows))
        self.assertEqual(meta['candidate_limit'], 'all')
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM documents').fetchone()[0], len(self.rows))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM term_index').fetchone()[0], len(self.rows))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM documents WHERE level IS NOT NULL").fetchone()[0], 0)

    def test_partial_and_stale_indices_fail_closed(self):
        sample = self.root / 'sample.sqlite'
        build_index(sample, candidate_limit=5, include_curated=False, imported_root=self.root)
        with self.assertRaisesRegex(ValueError, 'partial or stale'):
            research_with_knowledge('origin_word', db_path=sample, iterations=10, imported_root=self.root)
        manifest = json.loads((self.root / 'manifest.json').read_text())
        manifest['annotation'] = 'source revision changed'
        (self.root / 'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'partial or stale'):
            validate_full_index(self.path, imported_root=self.root)

    def test_missing_fts_record_is_not_full_knowledge_coverage(self):
        with sqlite3.connect(self.path) as db:
            db.execute('DELETE FROM term_index WHERE rowid=(SELECT MAX(rowid) FROM term_index)')
        with self.assertRaisesRegex(ValueError, 'partial or stale'):
            validate_full_index(self.path, imported_root=self.root)

    def test_curated_input_change_invalidates_runtime_cache(self):
        with sqlite3.connect(self.path) as db:
            # Add one curated record with a matching FTS row, but an old input
            # fingerprint. Imported count alone must not validate this cache.
            db.execute("INSERT INTO documents VALUES ('C','curated',1,'Algebra','{}')")
            rid = db.execute("SELECT rowid FROM documents WHERE id='C'").fetchone()[0]
            db.execute('INSERT INTO term_index(rowid,terms) VALUES (?,?)', (rid, 'curated'))
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('curated_input_sha256','old')")
        with self.assertRaisesRegex(ValueError, 'partial or stale'):
            validate_full_index(self.path, imported_root=self.root)

    def test_dynamic_retrieval_reaches_card_absent_from_initial_lexical_hits(self):
        corpus = IndexedCorpus(self.path)
        self.addCleanup(corpus.close)
        problem = KnowledgeMCTSProblem(corpus, 'origin_word', depth=4,
                                       retrieval_width=20, exploration_width=1, seed=1)
        state = problem.initial_state()
        first = problem.actions(state)
        root_trace = problem.trace[-1]
        self.assertIn('I000', root_trace['lexical_ids'])
        self.assertNotIn('I001', root_trace['lexical_ids'])
        next_state = problem.step(state, 'I000')
        second = problem.actions(next_state)
        self.assertIn('I001', problem.trace[-1]['lexical_ids'])
        self.assertIn('I001', second)
        self.assertNotIn('I000', second)
        self.assertNotEqual(root_trace['query'], problem.trace[-1]['query'])
        self.assertGreater(corpus.search_calls, 1)

    def test_real_mcts_uses_sources_and_reports_actual_tree_depth(self):
        report = research_with_knowledge('origin_word', db_path=self.path, iterations=150,
                  depth=4, retrieval_width=4, exploration_width=4, seed=11,
                  imported_root=self.root)
        self.assertEqual(report['mcts']['simulations'], 150)
        self.assertEqual(report['coverage']['indexed_imported'], len(self.rows))
        self.assertEqual(report['coverage']['all_records_examined_this_run'],
                         report['usage']['distinct_cards_loaded'] == len(self.rows))
        self.assertGreater(report['usage']['retrieval_calls'], 1)
        self.assertGreater(report['usage']['distinct_cards_selected_in_tree'], 0)
        self.assertEqual(report['usage']['selected_by_source_tier'],
                         {'unreviewed_import': report['usage']['distinct_cards_selected_in_tree']})
        observed = max([0] + [p['depth'] for p in report['paths']])
        self.assertEqual(report['usage']['actual_tree_depth'], observed)
        candidates = {cid for event in report['retrieval_trace'] for cid in event['candidate_ids']}
        for path in report['paths']:
            self.assertEqual(len(path['knowledge_ids']), len(set(path['knowledge_ids'])))
            self.assertTrue(set(path['knowledge_ids']) <= candidates)
        for card in report['knowledge_records']:
            self.assertIsNone(card['difficulty_level'])
            self.assertFalse(card['proof_verified_by_this_search'])
            self.assertEqual(card['verification_status'], 'pending')
            self.assertTrue(card['statement_sha256'])
        self.assertFalse(report['proof_verified'])
        repeat = research_with_knowledge('origin_word', db_path=self.path, iterations=150,
                  depth=4, retrieval_width=4, exploration_width=4, seed=11,
                  imported_root=self.root)
        self.assertEqual(report['paths'], repeat['paths'])
        self.assertEqual(report['retrieval_trace'], repeat['retrieval_trace'])

    def test_no_lexical_hits_still_explores_imported_corpus(self):
        report = research_with_knowledge('nothing_matches_987', db_path=self.path,
                    iterations=20, depth=3, seed=19, imported_root=self.root)
        self.assertGreater(report['usage']['distinct_exploration_hits'], 0)
        self.assertTrue(report['paths'])

    def test_tampered_shard_rejected_without_destroying_previous_index(self):
        old = self.path.read_bytes()
        (self.root / 'cards.json.gz').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            build_index(self.path, imported_root=self.root, include_curated=False)
        self.assertEqual(self.path.read_bytes(), old)

    def test_cached_partial_index_rebuilt_instead_of_silent_fallback(self):
        build_index(self.path, candidate_limit=2, include_curated=False, imported_root=self.root)
        # Avoid depending on the repository's curated catalog for this fixture.
        original_build = build_index
        with patch('math_mcts.indexed_mcts.build_index',
                   side_effect=lambda path, **kw: original_build(path, include_curated=False, **kw)):
            meta = ensure_full_index(self.path, imported_root=self.root)
        self.assertEqual(meta['actual_imported'], len(self.rows))

    def test_empty_filtered_scope_is_reported_without_curated_fallback(self):
        report = research_with_knowledge('origin_word', db_path=self.path,
                    iterations=5, depth=3, domain='nonexistent', imported_root=self.root)
        self.assertEqual(report['coverage']['eligible_scope'], 0)
        self.assertEqual(report['paths'], [])
        self.assertEqual(report['usage']['distinct_cards_selected_in_tree'], 0)

    def test_normal_collision_cli_uses_complete_corpus_entry(self):
        from math_mcts.__main__ import cmd_collide
        args = argparse.Namespace(curated_only=False, levels=None, important=False,
                    seed='origin_word', db=self.path, iterations=7, top_k=2,
                    random_seed=11, domain=None)
        with patch('math_mcts.indexed_mcts.research_with_knowledge',
                   return_value={'status': 'knowledge_search_leads_only'}) as run:
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_collide(args)
        run.assert_called_once_with('origin_word', db_path=self.path,
                      iterations=7, depth=2, top_k=2, seed=11, domain=None)


    def test_explicit_external_literature_is_mcts_searchable_and_not_trusted(self):
        from math_mcts.source_expansion import import_jsonl
        ext = self.root / "external.sqlite"
        source = self.root / "external.jsonl"
        row = {"source": "arXiv", "source_ref": "local-fixed-statement-v1",
               "source_url": "https://arxiv.org/abs/2601.00001",
               "license": "unverified", "locator": "paper/theorem/1",
               "name": "origin_word external lemma", "kind": "lemma",
               "statement": "The origin_word external lemma has strict hypotheses.",
               "authors": "Researcher One", "paper_title": "External paper",
               "source_provider": "TheoremSearch",
               "provider_url": "https://github.com/uw-math-ai/TheoremSearch"}
        source.write_text(json.dumps(row) + "\n", encoding="utf-8")
        import_jsonl(ext, source)
        report = research_with_knowledge(
            "origin_word", db_path=self.path, external_db_path=ext, iterations=30,
            depth=3, retrieval_width=12, exploration_width=2, seed=5,
            imported_root=self.root)
        self.assertEqual(report["coverage"]["indexed_imported"], len(self.rows))
        self.assertEqual(report["coverage"]["external_candidates_indexed"], 1)
        self.assertTrue(report["coverage"]["complete_imported_index"])
        self.assertGreater(report["usage"]["external_retrieval_calls"], 0)
        self.assertGreater(report["usage"]["distinct_external_lexical_hits"], 0)
        self.assertTrue(any(
            any(cid.startswith("EXT_") for cid in event["lexical_ids"])
            for event in report["retrieval_trace"]))
        self.assertFalse(report["proof_verified"])

class ExactFTSRetrievalTests(unittest.TestCase):
    def make_db(self, texts):
        from math_mcts.fts_retrieval import ExactFTSRetriever
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.execute('CREATE VIRTUAL TABLE term_index USING fts5(terms)')
        db.executemany('INSERT INTO term_index(terms) VALUES (?)', [(t,) for t in texts])
        return db, ExactFTSRetriever(db, sparse_limit=8)

    def test_randomized_top_k_agrees_with_original_including_phrase_tokens(self):
        rng = random.Random(2901)
        common = ['finite', 'group', 'matrix', 'left', 'right', 'energy']
        texts = [' '.join(rng.choices(common, k=rng.randint(1, 25))) +
                 ' rare_' + str(i % 79) for i in range(400)]
        _, retriever = self.make_db(texts)
        for _ in range(250):
            tokens = sorted(rng.sample(common, rng.randint(0, 6)) +
                            rng.sample(['rare_' + str(i) for i in range(90)],
                                       rng.randint(1, 3)))
            limit = rng.choice([1, 3, 10, 24, 100])
            self.assertEqual(retriever.search(tokens, limit),
                             retriever.full_rank(tokens, limit))
        self.assertGreater(retriever.counts['split_queries'], 0)

    def test_dense_cache_and_rowid_ties_preserve_exact_order(self):
        _, r = self.make_db(['common'] * 100 + ['common rarea', 'common rareb'])
        for tokens in (['common', 'rarea'], ['common', 'rareb']):
            self.assertEqual(r.search(tokens, 5), r.full_rank(tokens, 5))
        self.assertGreater(r.counts['dense_cache_hits'], 0)
        self.assertEqual(r.search(['common', 'missing'], 5),
                         r.full_rank(['common', 'missing'], 5))

    def test_oversized_sparse_union_falls_back_without_truncation(self):
        _, r = self.make_db(['sparse'] * 7 + ['other'] * 7)
        r.pool_limit = 5
        self.assertEqual(r.search(['other', 'sparse'], 3),
                         r.full_rank(['other', 'sparse'], 3))
        self.assertEqual(r.counts['pool_fallbacks'], 1)

    def test_explicit_domain_retains_original_filtered_query(self):
        db, r = self.make_db(['common rarea', 'common rareb', 'common'])
        db.execute('CREATE TABLE documents(domain TEXT)')
        db.executemany('INSERT INTO documents(domain) VALUES (?)', [('A',), ('B',), ('A',)])
        kw = dict(clause=' AND d.domain=?', values=('B',))
        self.assertEqual(r.search(['common', 'rarea'], 3, **kw),
                         r.full_rank(['common', 'rarea'], 3, **kw))
        self.assertEqual(r.counts['filtered_fallbacks'], 1)

    def test_empty_and_dense_only_queries(self):
        _, r = self.make_db(['common'] * 30)
        self.assertEqual(r.search(['missing'], 3), [])
        self.assertEqual(r.search(['common'], 3), r.full_rank(['common'], 3))
        self.assertGreater(r.counts['dense_only_queries'], 0)


if __name__ == '__main__':
    unittest.main()

