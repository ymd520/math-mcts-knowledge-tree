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

# --- v1.6.0 架构优化回归项 ---
from math_mcts.knowledge import _shard_index, _normalize_imported_domain
idx = _shard_index()
assert len(idx) > 8000, 'module index missing or incomplete'
assert idx.get('Mathlib.Algebra.GroupWithZero.Action.Basic'), 'index lookup failed'

# 多前缀加载: 跨领域碰撞可用, 领域标签已映射到精选库 7 域中文体系
mixed = KnowledgeTree.load_imported(
    module_prefix=['Mathlib.Algebra.Ring', 'Mathlib.Analysis.SpecialFunctions.Log'],
    include_curated=False)
dom_set = {c.domain_cn for c in mixed.concepts}
assert dom_set <= {'代数', '分析', '几何与拓扑', '概率与统计', '离散数学', '计算与优化', '数学基础'}, dom_set
assert {'代数', '分析'} <= dom_set
assert mixed.meta['import_scope'] == ['Mathlib.Algebra.Ring', 'Mathlib.Analysis.SpecialFunctions.Log']

# 领域映射表覆盖全部 27 个导入领域, 无一漏网
import collections
all_doms = set()
for f in m['files']:
    rows = json.loads(gzip.decompress((root/'math_mcts/data/imported'/f['shard']).read_bytes()))['concepts']
    for r in rows:
        all_doms.add(r['domain_en'])
unmapped = [d for d in all_doms if _normalize_imported_domain({'domain_en': d, 'domain_cn': d})[0] == d and d not in
            {'代数','分析','几何与拓扑','概率与统计','离散数学','计算与优化','数学基础'}]
# 允许的原文直通仅当映射表缺失; 此处要求映射表全覆盖
from math_mcts.knowledge import _IMPORT_DOMAIN_MAP
assert all_doms <= set(_IMPORT_DOMAIN_MAP), f'unmapped domains: {all_doms - set(_IMPORT_DOMAIN_MAP)}'

# find 精确查找在导入规模下正确
probe = mixed.concepts[0]
assert mixed.find(probe.cn) is probe and mixed.find(probe.en) is probe

# 碰撞懒候选: 初始化不再 O(N^2), 跨域对可被发现
from math_mcts import collide_concepts
pairs = collide_concepts(mixed, top_k=2, iterations=800)
assert pairs, 'no collision pairs found in mixed scope'
for a, b, score, _ in pairs:
    assert a.domain_cn != b.domain_cn
print('V1.6.0 ARCH CHECKS PASSED')
