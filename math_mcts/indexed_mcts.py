"""Corpus-backed MCTS: retrieve again at each search state, with an audit trail.

The FTS index covers all source records, but only bounded batches enter each
node. Actions select knowledge cards; they do not apply mathematical inference.
The generic numeric MCTS kernel remains usable without a knowledge database.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import time

from .attribution import source_credit
from .fast_index import build_index, terms_for, catalog_fingerprint
from .knowledge import IMPORTED_DIR, _normalize_imported_domain, _IMPORT_DOMAIN_MAP
from .mcts import Problem, mcts
from .vector_retrieval import VectorFTSRetriever

DEFAULT_CORPUS_DB = Path('.cache') / 'math_mcts' / 'full_corpus.sqlite'
_STOP = {'mathlib', 'theorem', 'lemma', 'def', 'instance', 'by', 'true',
         'false', 'type', 'prop', 'sort', 'forall', 'exists'}


def _tokens(text):
    return [t for t in terms_for(text) if t not in _STOP]


def _manifest(root):
    data = (Path(root) / 'manifest.json').read_bytes()
    manifest = json.loads(data)
    total = sum(item['card_count'] for item in manifest['files'])
    for key in ('expected_cards', 'imported_cards'):
        if key in manifest and manifest[key] != total:
            raise ValueError('Imported manifest total mismatch')
    return hashlib.sha256(data).hexdigest(), total


def validate_full_index(db_path, *, imported_root=IMPORTED_DIR):
    """Reject a missing, partial, stale, or internally miscounted corpus view."""
    fingerprint, expected = _manifest(imported_root)
    path = Path(db_path)
    if not path.is_file():
        raise ValueError('Full knowledge index missing: ' + str(path))
    try:
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
            metadata = dict(db.execute('SELECT key,value FROM metadata'))
            counts = dict(db.execute('SELECT tier,COUNT(*) FROM documents GROUP BY tier'))
            fts_count = db.execute('SELECT COUNT(*) FROM term_index').fetchone()[0]
            orphan = db.execute('SELECT 1 FROM term_index t LEFT JOIN documents d '
                                'ON d.rowid=t.rowid WHERE d.rowid IS NULL LIMIT 1').fetchone()
    except sqlite3.DatabaseError as exc:
        raise ValueError('Invalid knowledge index; rebuild from the source shards') from exc
    if (metadata.get('imported_manifest_sha256') != fingerprint
            or metadata.get('indexed_all_imports') != '1'
            or not set(counts) <= {'curated', 'unreviewed_import'}
            or metadata.get('curated_count') != str(counts.get('curated', 0))
            or counts.get('unreviewed_import', 0) != expected
            or fts_count != sum(counts.values()) or orphan
            or (counts.get('curated', 0) and metadata.get('curated_input_sha256') != catalog_fingerprint())
            or metadata.get('unreviewed_candidate_count') != str(expected)
            or metadata.get('available_imported_count') != str(expected)):
        raise ValueError('Knowledge index is partial or stale; rebuild with '
                         'tools/build_search_index.py --db PATH (omit --candidate-limit)')
    return {**metadata, 'actual_imported': expected,
            'actual_curated': counts.get('curated', 0),
            'actual_total': sum(counts.values())}


def ensure_full_index(db_path=DEFAULT_CORPUS_DB, *, imported_root=IMPORTED_DIR):
    """Rebuild the dedicated runtime cache when its complete-source view is stale."""
    try:
        return validate_full_index(db_path, imported_root=imported_root)
    except ValueError:
        build_index(db_path, imported_root=imported_root)
        return validate_full_index(db_path, imported_root=imported_root)


class IndexedCorpus:
    """Read a fixed database snapshot; never allocate the whole Concept catalog."""

    def __init__(self, db_path, *, domain=None):
        self.db_path = Path(db_path)
        self.db = sqlite3.connect(self.db_path.resolve().as_uri() + '?mode=ro', uri=True)
        self.db.execute('BEGIN')
        self.domain = domain
        self.metadata = dict(self.db.execute('SELECT key,value FROM metadata'))
        self.total = self.db.execute('SELECT COUNT(*) FROM documents').fetchone()[0]
        if not self.total:
            self.db.close()
            raise ValueError('Knowledge index is empty')
        self.imported = self.db.execute("SELECT COUNT(*) FROM documents WHERE tier='unreviewed_import'").fetchone()[0]
        self.max_rowid = self.db.execute('SELECT MAX(rowid) FROM documents').fetchone()[0]
        self._cache = OrderedDict()
        # Cache belongs to this immutable read transaction, never another index.
        self._qcache = OrderedDict()
        self.query_cache_hits = 0
        self.retriever = VectorFTSRetriever(self.db, self.max_rowid)
        self.lexical_record_load_seconds = 0.
        self.lexical_decode_seconds = 0.
        self.loaded_ids = set()
        self.retrieved_ids = set()
        self.explored_ids = set()
        self.search_calls = 0
        self.sample_calls = 0
        self._domain_values = None
        if domain:
            self._domain_values = sorted({key for key, value in _IMPORT_DOMAIN_MAP.items()
                                          if value[0] == domain} |
                                         {domain} |
                                         {value[1] for value in _IMPORT_DOMAIN_MAP.values()
                                          if value[0] == domain})
        clause, values = self._filter()
        self.scope_count = self.db.execute('SELECT COUNT(*) FROM documents d WHERE 1=1' + clause, values).fetchone()[0]

    def close(self):
        self.db.close()

    def _filter(self):
        if self._domain_values is None:
            return '', ()
        return (' AND d.domain IN (' + ','.join('?' for _ in self._domain_values) + ')', tuple(self._domain_values))

    def _decode(self, item):
        cid, blob, tier, level = item
        self.loaded_ids.add(cid)
        if cid in self._cache:
            self._cache.move_to_end(cid)
            return self._cache[cid]
        row = json.loads(blob)
        if row['id'] != cid:
            raise ValueError('Indexed ID differs from the source record')
        domain = _normalize_imported_domain(row)[0] if tier == 'unreviewed_import' else row.get('domain_cn', '')
        statement = row.get('formal') or row.get('definition') or ''
        card = {'id': cid, 'name': row.get('cn') or row.get('en'),
                'english_name': row.get('en', ''), 'domain': domain,
                'module': row.get('module', ''), 'statement': statement,
                'statement_sha256': hashlib.sha256(statement.encode()).hexdigest(),
                'source_tier': tier, 'difficulty_level': level,
                'verification_status': row.get('verification_status', ''),
                'curation_status': row.get('curation_status', ''),
                'attribution': source_credit(row, tier=tier),
                'proof_verified_by_this_search': False}
        card['_tokens'] = frozenset(_tokens(' '.join(str(row.get(k, '')) for k in
                                  ('cn', 'en', 'definition', 'formal', 'module', 'branch_cn', 'topic_cn'))))
        self._cache[cid] = card
        if len(self._cache) > 1024:
            self._cache.popitem(last=False)
        return card

    def get(self, cid):
        if cid in self._cache:
            self._cache.move_to_end(cid)
            return self._cache[cid]
        row = self.db.execute('SELECT id,record,tier,level FROM documents WHERE id=?', (cid,)).fetchone()
        if row is None:
            raise KeyError(cid)
        return self._decode(row)

    def search(self, query, limit):
        self.search_calls += 1
        tokens = _tokens(query)[:24]
        if not tokens:
            return []
        tokens = list(dict.fromkeys(tokens))
        key = (tuple(tokens), limit)
        if key in self._qcache:
            self.query_cache_hits += 1
            self._qcache.move_to_end(key)
            return [self.get(cid) for cid in self._qcache[key]]
        match = ' OR '.join('"' + t.replace('"', '""') + '"' for t in tokens)
        clause, values = self._filter()
        selected = self.retriever.search(tokens, limit, clause=clause, values=values)
        # Cache empty hits too; repeated misses must not re-run FTS.
        if not selected:
            self._remember_query(key, ())
            return []
        # One bounded IN lookup rather than one SQL round-trip per ranked hit.
        order = [item[0] for item in selected]
        placeholders = ','.join('?' for _ in order)
        loading_at = time.perf_counter()
        loaded = {rid: (cid, blob, tier, lvl)
                  for rid, cid, blob, tier, lvl in self.db.execute(
                      'SELECT rowid,id,record,tier,level FROM documents WHERE rowid IN ('
                      + placeholders + ')', order)}
        self.lexical_record_load_seconds += time.perf_counter() - loading_at
        rows = [loaded[rid] for rid in order]
        self.retrieved_ids.update(row[0] for row in rows)
        self._remember_query(key, tuple(row[0] for row in rows))
        decoding_at = time.perf_counter()
        cards = [self._decode(row) for row in rows]
        self.lexical_decode_seconds += time.perf_counter() - decoding_at
        return cards

    def _remember_query(self, key, ids):
        self._qcache[key] = ids
        if len(self._qcache) > 256:
            self._qcache.popitem(last=False)

    def sample(self, rng, limit):
        """Random rowid probes, not ORDER BY RANDOM() over the full corpus.

        Every indexed record has positive admission probability. No claim of
        finite-budget exhaustive coverage; gaps merely produce unused probes.
        Domain filtering may return fewer than limit cards in a bounded run.
        """
        self.sample_calls += 1
        clause, values = self._filter()
        selected = {}
        for _ in range(max(20, limit * 12)):
            if len(selected) >= limit:
                break
            rid = rng.randint(1, self.max_rowid)
            row = self.db.execute('SELECT d.id,d.record,d.tier,d.level FROM documents d '
                                  'WHERE d.rowid=?' + clause, (rid, *values)).fetchone()
            if row is not None:
                selected[row[0]] = row
        self.explored_ids.update(selected)
        return [self._decode(row) for row in selected.values()]

    def public_card(self, cid):
        return {k: v for k, v in self.get(cid).items() if not k.startswith('_')}


@dataclass(frozen=True)
class KnowledgeState:
    ids: tuple[str, ...] = ()


class KnowledgeMCTSProblem(Problem):
    """Each action appends an actually retrieved card to a research path.

    The score measures lexical relevance, adjacent shared vocabulary and domain
    breadth. It does NOT measure valid theorem applicability or originality.
    """
    value_op = 'max'

    def __init__(self, corpus, objective, *, depth=20, retrieval_width=24,
                 exploration_width=8, seed=7):
        if type(depth) is not int or not 1 <= depth <= 100:
            raise ValueError('depth must be 1..100')
        if type(retrieval_width) is not int or not 1 <= retrieval_width <= 200:
            raise ValueError('retrieval_width must be 1..200')
        if type(exploration_width) is not int or not 1 <= exploration_width <= 100:
            raise ValueError('exploration_width must be 1..100')
        self.corpus = corpus
        self.objective = objective
        self.objective_tokens = set(_tokens(objective))
        self.depth = depth
        self.retrieval_width = retrieval_width
        self.exploration_width = exploration_width
        self.seed = seed
        self.trace = []
        self.selected_ids = set()
        self.maximum_expanded_depth = 0
        self._actions = OrderedDict()

    def initial_state(self):
        return KnowledgeState()

    def terminal(self, state):
        return len(state.ids) >= self.depth

    def _query(self, state):
        # Keep the user objective, then re-query using the current branch's
        # recent cards. Never freeze the root shortlist for the entire run.
        context = []
        for cid in state.ids[-2:]:
            c = self.corpus.get(cid)
            context.extend([c['name'], c['english_name'], c['module']])
        return ' '.join([self.objective, *context])

    def actions(self, state):
        if self.terminal(state):
            return []
        if state in self._actions:
            self._actions.move_to_end(state)
            return self._actions[state]
        query = self._query(state)
        digest = hashlib.sha256(json.dumps([self.seed, state.ids], ensure_ascii=False).encode()).digest()
        rng = random.Random(int.from_bytes(digest[:16], 'big'))
        lexical = self.corpus.search(query, self.retrieval_width)
        exploratory = self.corpus.sample(rng, self.exploration_width)
        seen = set(state.ids)
        cards = {c['id']: c for c in [*lexical, *exploratory] if c['id'] not in seen}
        # Round-robin domains so a single abundant field does not monopolize
        # progressive widening. Within each field, use explicit lexical scores.
        groups = {}
        for c in sorted(cards.values(), key=lambda c: (-self._card_score(c, state), c['id'])):
            groups.setdefault(c['domain'], []).append(c['id'])
        actions = []
        while any(groups.values()):
            for group in groups.values():
                if group:
                    actions.append(group.pop(0))
        self.trace.append({'state_ids': list(state.ids), 'depth': len(state.ids),
                           'query': query, 'lexical_ids': [c['id'] for c in lexical],
                           'exploration_ids': [c['id'] for c in exploratory],
                           'candidate_ids': actions})
        self._actions[state] = actions
        if len(self._actions) > 256:
            self._actions.popitem(last=False)
        return actions

    def iter_actions(self, state):
        return iter(self.actions(state))

    def step(self, state, action):
        self.corpus.get(action)  # Fail if an action has no source card.
        self.selected_ids.add(action)
        self.maximum_expanded_depth = max(self.maximum_expanded_depth, len(state.ids) + 1)
        return KnowledgeState(state.ids + (action,))

    def _card_score(self, card, state):
        tokens = card['_tokens']
        relevance = len(tokens & self.objective_tokens) / max(1, len(self.objective_tokens))
        coherence = 0.
        if state.ids:
            last = self.corpus.get(state.ids[-1])
            shared = tokens & last['_tokens']
            coherence = len(shared) / max(1, len(tokens | last['_tokens']))
        return relevance + coherence

    def reward(self, state):
        if not state.ids:
            return 0.
        cards = [self.corpus.get(cid) for cid in state.ids]
        relevance = sum(len(c['_tokens'] & self.objective_tokens) /
                        max(1, len(self.objective_tokens)) for c in cards) / len(cards)
        pairs = list(zip(cards, cards[1:]))
        coherence = sum(len(a['_tokens'] & b['_tokens']) /
                        max(1, len(a['_tokens'] | b['_tokens'])) for a, b in pairs) / max(1, len(pairs))
        breadth = len({c['domain'] for c in cards}) / len(cards)
        return .5 * relevance + .2 * coherence + .1 * breadth + .2 * len(cards) / self.depth


def research_with_knowledge(objective='', *, db_path=None, iterations=1000,
                            depth=20, retrieval_width=24, exploration_width=8,
                            seed=7, top_k=5, domain=None,
                            imported_root=IMPORTED_DIR, external_db_path=None):
    """The standard full-corpus research entry point, with fail-closed coverage.

    An omitted db_path manages a full runtime cache automatically. An explicitly
    supplied DB is validated and never silently replaced by a smaller catalog.
    Returned paths are knowledge-selection leads, never proof certificates.
    """
    if type(iterations) is not int or iterations < 1:
        raise ValueError('iterations must be positive')
    if type(top_k) is not int or not 1 <= top_k <= 100:
        raise ValueError('top_k must be 1..100')
    start = time.perf_counter()
    if db_path is None:
        path = DEFAULT_CORPUS_DB
        coverage = ensure_full_index(path, imported_root=imported_root)
    else:
        path = Path(db_path)
        coverage = validate_full_index(path, imported_root=imported_root)
    validated_at = time.perf_counter()
    corpus = IndexedCorpus(path, domain=domain)
    if external_db_path is not None:
        from .literature_bridge import HybridCorpus
        try:
            corpus = HybridCorpus(corpus, external_db_path)
        except Exception:
            corpus.close()
            raise
    opened_at = time.perf_counter()
    try:
        problem = KnowledgeMCTSProblem(corpus, objective, depth=depth,
                                      retrieval_width=retrieval_width,
                                      exploration_width=exploration_width, seed=seed)
        path_actions, root = mcts(problem, iterations=iterations, max_depth=depth,
                                 seed=seed, action_mode='stream',
                                 widening_k=1., widening_alpha=.25)
        searched_at = time.perf_counter()
        # Report actual tree nodes, not completed random-rollout depth.
        nodes = [root]
        states = {}
        while nodes:
            node = nodes.pop()
            if node.state.ids:
                states[node.state.ids] = problem.reward(node.state)
            nodes.extend(node.children)
        # Keep distinct terminal/deep paths; prefixes of a better path are not
        # additional discoveries. This is only heuristic lead ranking.
        ranked = sorted(states, key=lambda s: (-len(s), -states[s], s))
        paths = []
        for state in ranked:
            if any(tuple(p['knowledge_ids'][:len(state)]) == state for p in paths):
                continue
            paths.append({'knowledge_ids': list(state), 'depth': len(state),
                          'heuristic_score': states[state]})
            if len(paths) == top_k:
                break
        final_ids = {cid for p in paths for cid in p['knowledge_ids']}
        # Keep all knowledge actually selected and scored in the tree, even
        # when a different branch becomes the final heuristic winner.
        reported_ids = sorted(problem.selected_ids)
        tiers_used = {}
        for cid in problem.selected_ids:
            tier = corpus.get(cid)['source_tier']
            tiers_used[tier] = tiers_used.get(tier, 0) + 1
        report = {'status': 'knowledge_search_leads_only', 'proof_verified': False,
                'objective': objective, 'seed': seed,
                'coverage': {'indexed_total': corpus.total, 'indexed_imported': corpus.imported,
                             'manifest_imported': coverage['actual_imported'],
                             'complete_imported_index': True,
                             'imported_manifest_sha256': coverage['imported_manifest_sha256'],
                             'domain_filter': domain, 'eligible_scope': corpus.scope_count,
                             'all_records_examined_this_run': len(corpus.loaded_ids) == corpus.total,
                             'external_candidates_indexed': getattr(corpus, 'external_count', 0),
                             'external_candidates_by_source': getattr(corpus, 'source_counts', {}),
                             'external_cache_enabled': external_db_path is not None},
                'usage': {'retrieval_calls': corpus.search_calls,
                          'global_exploration_calls': corpus.sample_calls,
                          'primary_query_cache_hits': corpus.query_cache_hits,
                          'distinct_cards_loaded': len(corpus.loaded_ids),
                          'distinct_lexical_hits': len(corpus.retrieved_ids),
                          'distinct_exploration_hits': len(corpus.explored_ids),
                          'external_retrieval_calls': getattr(corpus, 'external_search_calls', 0),
                          'distinct_external_lexical_hits': len(getattr(corpus, 'external_retrieved_ids', ())),
                          'distinct_cards_selected_in_tree': len(problem.selected_ids),
                          'selected_by_source_tier': tiers_used,
                          'actual_tree_depth': problem.maximum_expanded_depth},
                'mcts': root.stats, 'paths': paths,
                'kernel_extracted_path': path_actions,
                'knowledge_records': [{**corpus.public_card(cid),
                                       'on_reported_path': cid in final_ids}
                                      for cid in reported_ids],
                'retrieval_trace': problem.trace,
                'score_meaning': 'lexical relevance, shared vocabulary, domain breadth and depth; not mathematical validity or novelty',
                'retrieval_profile': {**corpus.retriever.profile(),
                    'lexical_record_load_seconds': corpus.lexical_record_load_seconds,
                    'lexical_decode_seconds': corpus.lexical_decode_seconds},
                'elapsed_seconds': 0.}
        finished_at = time.perf_counter()
        report['timings_seconds'] = {
            'index_validation_or_build': validated_at - start,
            'corpus_open': opened_at - validated_at,
            'tree_search': searched_at - opened_at,
            'report_assembly': finished_at - searched_at}
        report['elapsed_seconds'] = finished_at - start
        return report
    finally:
        corpus.close()

