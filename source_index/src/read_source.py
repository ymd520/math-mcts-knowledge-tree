"""Read exact unmodified source around a node from the bundled archive."""
import argparse,json,pathlib,sqlite3,tarfile
from storage import ensure_database
ensure_database()
ROOT=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('node');p.add_argument('--context',type=int,default=30);a=p.parse_args()
c=sqlite3.connect(ROOT/'data/knowledge.sqlite')
r=c.execute('SELECT source,payload FROM nodes WHERE id=?',(a.node,)).fetchone()
if not r:p.error('unknown node')
meta=json.loads(r[1]);path=meta.get('path')
if not path:p.error('this node has no source text; choose a module or declaration')
with tarfile.open(ROOT/'vendor/mathlib4.tar.gz') as t:
 m=next(x for x in t.getmembers() if x.isfile() and x.name.split('/',1)[-1]==path)
 lines=t.extractfile(m).read().decode().splitlines()
line=meta.get('line',1);start=max(0,line-1-max(0,a.context)//2);end=min(len(lines),line+max(0,a.context))
print(r[0]);print('Source locator only; this command does not elaborate or check Lean.')
for i in range(start,end):print(f'{i+1}: {lines[i]}')
