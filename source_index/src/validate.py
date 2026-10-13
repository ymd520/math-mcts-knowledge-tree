import collections,json,pathlib,sqlite3
from storage import ensure_database
ensure_database()
ROOT=pathlib.Path(__file__).resolve().parents[1]
db=sqlite3.connect(ROOT/'data/knowledge.sqlite')
assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
for col in ['src','dst']:
 assert db.execute(f'SELECT count(*) FROM edges e LEFT JOIN nodes n ON e.{col}=n.id WHERE n.id IS NULL').fetchone()[0]==0
contains=list(db.execute("SELECT src,dst FROM edges WHERE relation='contains'"));deg=collections.Counter();children=collections.defaultdict(list)
ids={r[0] for r in db.execute('SELECT id FROM nodes')}
for a,b in contains:children[a].append(b);deg[b]+=1
queue=collections.deque(n for n in ids if not deg[n]);visited=0
while queue:
 a=queue.popleft();visited+=1
 for b in children[a]:
  deg[b]-=1
  if deg[b]==0:queue.append(b)
assert visited==len(ids),'contains cycle'
assert db.execute("SELECT count(*) FROM nodes WHERE kind IN ('module','declaration') AND source='' ").fetchone()[0]==0
seen={'root'};q=collections.deque(seen)
while q:
 for (b,) in db.execute("SELECT dst FROM edges WHERE src=? AND relation IN ('contains','source_map')",(q.popleft(),)):
  if b not in seen:seen.add(b);q.append(b)
assert len(seen)==len(ids)
print(json.dumps({'integrity':'ok','edge_endpoints':'ok','contains_dag':'ok','source_locators':'ok','reachable_nodes':len(seen)},indent=2))
