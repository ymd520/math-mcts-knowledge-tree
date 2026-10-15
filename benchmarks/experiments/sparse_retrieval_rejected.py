"""Exact OR/BM25 top-k using cached dense queries and complete sparse postings.

For an OR of disjoint phrase sets D and S, any row not matching S retains
its D-only BM25 score. Therefore top-k(D) union ALL matching rows(S) contains
top-k(D OR S). Re-score that union with the original SQLite expression and
the original rowid tie-break. Never truncate sparse matches silently.

This relies on FTS5's unweighted BM25 phrase sum, not arbitrary rank functions.
See https://www.sqlite.org/fts5.html#the_bm25_function . No semantic filtering.
"""
from collections import OrderedDict
from collections import defaultdict
from time import perf_counter


def expression(tokens):
    return ' OR '.join('"' + t.replace('"', '""') + '"' for t in tokens)


class ExactFTSRetriever:
    def __init__(self, db, *, sparse_limit=128, pool_limit=1024):
        self.db = db
        self.sparse_limit = sparse_limit
        self.pool_limit = pool_limit
        self._postings = OrderedDict()
        self._dense = OrderedDict()
        self.counts = defaultdict(int)
        self.seconds = defaultdict(float)

    @staticmethod
    def _put(cache, key, value, cap):
        cache[key] = value
        cache.move_to_end(key)
        if len(cache) > cap:
            cache.popitem(last=False)

    def _sparse_rows(self, token):
        if token in self._postings:
            self.counts['posting_cache_hits'] += 1
            self._postings.move_to_end(token)
            return self._postings[token]
        start = perf_counter()
        rows = self.db.execute(
            'SELECT rowid FROM term_index WHERE term_index MATCH ? LIMIT ?',
            (expression([token]), self.sparse_limit + 1)).fetchall()
        self.seconds['posting_lookup'] += perf_counter() - start
        self.counts['posting_queries'] += 1
        # None means dense. A truncated prefix is NEVER used as full postings.
        value = tuple(r[0] for r in rows) if len(rows) <= self.sparse_limit else None
        self._put(self._postings, token, value, 512)
        return value

    def full_rank(self, tokens, limit, *, clause='', values=()):
        start = perf_counter()
        join = ' JOIN documents d ON d.rowid=term_index.rowid' if clause else ''
        rows = self.db.execute(
            'SELECT term_index.rowid FROM term_index' + join +
            ' WHERE term_index MATCH ?' + clause +
            ' ORDER BY bm25(term_index),term_index.rowid LIMIT ?',
            (expression(tokens), *values, limit)).fetchall()
        self.seconds['full_match_and_rank'] += perf_counter() - start
        self.counts['full_rank_queries'] += 1
        return rows

    def search(self, tokens, limit, *, clause='', values=()):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('retrieval limit must be 1..200')
        if not tokens:
            return []
        if clause:
            self.counts['filtered_fallbacks'] += 1
            return self.full_rank(tokens, limit, clause=clause, values=values)
        dense, sparse = [], set()
        has_sparse = False
        for token in tokens:
            rows = self._sparse_rows(token)
            if rows is None:
                dense.append(token)
            else:
                has_sparse = True
                sparse.update(rows)
            if len(sparse) + limit > self.pool_limit:
                self.counts['pool_fallbacks'] += 1
                return self.full_rank(tokens, limit)
        if not has_sparse:
            self.counts['dense_only_queries'] += 1
            return self.full_rank(tokens, limit)
        if dense:
            key = (tuple(dense), limit)
            if key in self._dense:
                self.counts['dense_cache_hits'] += 1
                self._dense.move_to_end(key)
                dense_rows = self._dense[key]
            else:
                dense_rows = self.full_rank(dense, limit)
                self._put(self._dense, key, dense_rows, 256)
            sparse.update(r[0] for r in dense_rows)
        if not sparse:
            return []
        self.counts['split_queries'] += 1
        self.counts['candidate_rows_scored'] += len(sparse)
        selected = []
        ids = sorted(sparse)
        start = perf_counter()
        # Bounded internal integer rowids only (never user text). A literal IN
        # list avoids old SQLite variable limits without scanning MATCH once
        # per batch. rowid+0 prevents an IN-driven fresh FTS cursor per row,
        # which would repeatedly recompute query-wide BM25 statistics.
        literals = ','.join(str(int(rid)) for rid in ids)
        selected = self.db.execute(
            'SELECT rowid,bm25(term_index) FROM term_index '
            'WHERE term_index MATCH ? AND (rowid+0) IN (' + literals + ')',
            (expression(tokens),)).fetchall()
        selected.sort(key=lambda r: (r[1], r[0]))
        self.seconds['candidate_match_and_rank'] += perf_counter() - start
        return [(rid,) for rid, _ in selected[:limit]]

    def profile(self):
        return {'strategy': 'exact_dense_plus_complete_sparse',
                'counts': dict(self.counts), 'seconds': dict(self.seconds),
                'sparse_limit': self.sparse_limit, 'pool_limit': self.pool_limit}
