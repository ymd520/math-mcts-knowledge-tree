import gzip,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts import KnowledgeTree,search_concepts
root=Path(__file__).resolve().parents[1]
m=json.loads((root/'math_mcts/data/imported/manifest.json').read_text())
assert m['imported_cards']==234576 and not m['errors']
count=0;ids=set();names=set();hashes=set()
for f in m['files']:
 raw=gzip.decompress((root/f['raw_archive']).read_bytes())
 assert len(raw)==f['source_bytes'] and hashlib.sha256(raw).hexdigest()==f['source_sha256']
 data=(root/'math_mcts/data/imported'/f['shard']).read_bytes()
 assert hashlib.sha256(data).hexdigest()==f['shard_sha256']
 rows=json.loads(gzip.decompress(data))['concepts'];assert len(rows)==f['card_count']
 for row in rows:
  assert row['id'] not in ids;ids.add(row['id'])
  assert row['en'] not in names;names.add(row['en'])
  original=row['original_metadata'];h=original['陈述SHA256']
  assert h not in hashes;hashes.add(h)
  if original['类型']=='upstream_theorem':
   assert hashlib.sha256(row['formal'].removeprefix('theorem '+row['en']).strip().encode()).hexdigest()==h
  assert row['prereq']==[]
  assert row['reference_relation']=='statement_symbol_reference_not_proof_dependency'
 count+=len(rows)
assert count==234576
scope=KnowledgeTree.load_imported(module_prefix='Mathlib.Algebra.GroupWithZero.Action.Basic',include_curated=False)
assert scope.concepts and not scope.check_integrity()
results=search_concepts(scope,'smul',top_k=3)
assert results and all(c.verification_status for c,_,_ in results)
print('ALL IMPORT CHECKS PASSED',count,'scoped concepts',len(scope.concepts))
