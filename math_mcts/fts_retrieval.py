"""Reference full-table SQLite OR/BM25 ranking and stage timing."""
from collections import defaultdict
from time import perf_counter


def expression(tokens):
    return ' OR '.join('"' + t.replace('"', '""') + '"' for t in tokens)


class ReferenceFTSRetriever:
    def __init__(self, db, *, pool_limit=4096):
        self.db = db
        self.pool_limit = pool_limit
        self.counts = defaultdict(int)
        self.seconds = defaultdict(float)

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
