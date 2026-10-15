"""Optional bounded NumPy cache of SQLite BM25 phrase contributions.

Whole-table scope, original phrase order, conservative roundoff guard,
original-query SQLite rescoring and deterministic rowid ties are retained.
Without NumPy (or outside memory/range limits), use the reference SQL.
"""
from collections import OrderedDict
from time import perf_counter

from .fts_retrieval import ReferenceFTSRetriever, expression


class VectorFTSRetriever(ReferenceFTSRetriever):
    def __init__(self, db, max_rowid, *, cache_bytes=64 * 1024 * 1024,
                 pool_limit=4096, use_numpy=True):
        super().__init__(db, pool_limit=pool_limit)
        self.max_rowid = max_rowid
        self.cache_bytes = cache_bytes
        self.cached_bytes = 0
        self._terms = OrderedDict()
        self.np = None
        self.disabled_reason = 'explicit_reference_backend'
        if use_numpy:
            try:
                import numpy as np
                self.np = np
                self.disabled_reason = None
            except ImportError:
                self.disabled_reason = 'numpy_unavailable'
        # Bound work buffers as well as cached contributions; huge rowid gaps
        # must never turn a small corpus into an enormous allocation.
        if max_rowid < 1 or (max_rowid + 1) * 8 > cache_bytes // 4:
            self.disabled_reason = 'rowid_range_exceeds_buffer_budget'
        self.enabled = self.np is not None and self.disabled_reason is None

    def _term_scores(self, token):
        if token in self._terms:
            self.counts['term_cache_hits'] += 1
            self._terms.move_to_end(token)
            return self._terms[token][0]
        np = self.np
        start = perf_counter()
        cursor = self.db.execute(
            'SELECT rowid,bm25(term_index) FROM term_index WHERE term_index MATCH ?',
            (expression([token]),))
        pairs = np.fromiter(cursor, dtype=[('rid', np.int64), ('score', np.float64)])
        ids, values = pairs['rid'], pairs['score']
        if len(ids) and (int(ids.min()) < 1 or int(ids.max()) > self.max_rowid):
            raise MemoryError('rowids outside allocated score buffer')
        if not np.isfinite(values).all():
            raise ArithmeticError('nonfinite SQLite BM25 phrase score')
        if len(ids) > (self.max_rowid + 1) // 16:
            scores = np.zeros(self.max_rowid + 1, dtype=np.float64)
            scores[ids] = values
            data, size = (None, scores), scores.nbytes
        else:
            positions, scores = ids.copy(), values.copy()
            data, size = (positions, scores), positions.nbytes + scores.nbytes
        self.seconds['term_score_loading'] += perf_counter() - start
        self.counts['term_score_queries'] += 1
        if size <= self.cache_bytes:
            while self._terms and (self.cached_bytes + size > self.cache_bytes or
                                   len(self._terms) >= 512):
                _, (_, old_size) = self._terms.popitem(last=False)
                self.cached_bytes -= old_size
                self.counts['term_cache_evictions'] += 1
            self._terms[token] = (data, size)
            self.cached_bytes += size
        return data

    def search(self, tokens, limit, *, clause='', values=()):
        if not tokens:
            return []
        if clause or not self.enabled:
            self.counts['reference_queries'] += 1
            return self.full_rank(tokens, limit, clause=clause, values=values)
        if type(limit) is not int or limit < 1:
            raise ValueError('retrieval limit must be positive')
        np = self.np
        try:
            scores = np.zeros(self.max_rowid + 1, dtype=np.float64)
            for token in tokens:
                positions, contribution = self._term_scores(token)
                start = perf_counter()
                if positions is None:
                    np.add(scores, contribution, out=scores)
                else:
                    scores[positions] += contribution
                self.seconds['vector_accumulation'] += perf_counter() - start
            start = perf_counter()
            matched = int(np.count_nonzero(scores < 0.))
            if not matched:
                return []
            cutoff = (float(np.partition(scores, limit - 1)[limit - 1])
                      if matched > limit else 0.)
            # SQLite re-scores ALL rows near the cutoff, not an arbitrary
            # prefix of a tied group. Wide ties fall back to reference SQL.
            guard = 1e-10 * (1. + abs(float(scores.min())))
            candidates = np.flatnonzero((scores < 0.) & (scores <= cutoff + guard))
            self.seconds['vector_candidate_selection'] += perf_counter() - start
            if len(candidates) > self.pool_limit:
                self.counts['wide_tie_fallbacks'] += 1
                return self.full_rank(tokens, limit)
            self.counts['vector_queries'] += 1
            self.counts['candidate_rows_scored'] += len(candidates)
            start = perf_counter()
            literals = ','.join(str(int(rid)) for rid in candidates)
            ranked = self.db.execute(
                'SELECT rowid,bm25(term_index) FROM term_index '
                'WHERE term_index MATCH ? AND (rowid+0) IN (' + literals + ') '
                'ORDER BY bm25(term_index),rowid LIMIT ?',
                (expression(tokens), limit)).fetchall()
            self.seconds['candidate_match_and_rank'] += perf_counter() - start
            return [(rid,) for rid, _ in ranked]
        except MemoryError:
            self._terms.clear()
            self.cached_bytes = 0
            self.enabled = False
            self.disabled_reason = 'allocation_or_rowid_range_fallback'
            self.counts['memory_fallbacks'] += 1
            return self.full_rank(tokens, limit)

    def profile(self):
        return {'strategy': 'numpy_phrase_scores_with_sqlite_rescoring' if self.enabled else
                            'sqlite_reference',
                'numpy_version': self.np.__version__ if self.np is not None else None,
                'disabled_reason': self.disabled_reason,
                'counts': dict(self.counts), 'seconds': dict(self.seconds),
                'cache_bytes': self.cached_bytes, 'cache_budget_bytes': self.cache_bytes,
                'pool_limit': self.pool_limit}
