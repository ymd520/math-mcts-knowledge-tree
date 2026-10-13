"""v1.11.0 补丁2: 删除与 v1.10.0 supplement 卡同名同级的 20 条重复, 引用重指向 supplement 卡."""
import json
import shutil
import gzip
from pathlib import Path

REPO = '/home/hatch/workspace/math-mcts-knowledge-tree'
P = REPO + '/math_mcts/data/knowledge.json'
shutil.copy(P, '/tmp/knowledge_backup_20261014_lv123_dedup2.json')
tree = json.load(open(P))

from math_mcts.catalog import PACK_DIR, name_key

sup_id_by_name = {}
for p in PACK_DIR.glob('*.json.gz'):
    pack = json.loads(gzip.open(p, 'rt').read())
    for row in pack['concepts']:
        sup_id_by_name.setdefault(name_key(row['cn']), row['id'])

# 新 LV 条目中与 supplement 卡同名的 -> 删, 记 remap
drop_ids = set()
remap = {}
for c in tree['concepts']:
    if c['id'].startswith('LV') and name_key(c['cn']) in sup_id_by_name:
        drop_ids.add(c['id'])
        remap[c['id']] = sup_id_by_name[name_key(c['cn'])]
        print(f'DROP {c["id"]} "{c["cn"]}" L{c["level"]} -> sup {remap[c["id"]]}')
print('drop count:', len(drop_ids))

# 所有条目的 prereq 重指向
n_fix = 0
for c in tree['concepts']:
    new_pre = []
    for pid in c['prereq']:
        if pid in remap:
            if remap[pid] != c['id'] and remap[pid] not in new_pre:
                new_pre.append(remap[pid])
                n_fix += 1
        elif pid not in new_pre:
            new_pre.append(pid)
    c['prereq'] = new_pre

tree['concepts'] = [c for c in tree['concepts'] if c['id'] not in drop_ids]
json.dump(tree, open(P, 'w'), ensure_ascii=False)
print(f'remapped {n_fix} prereq refs, total now {len(tree["concepts"])}')

from math_mcts import KnowledgeTree
t = KnowledgeTree.load()
errs = t.check_integrity()
print('integrity:', errs if errs else 'OK')
base = KnowledgeTree.load(include_supplements=False)
print('dup groups base/tree:', base.inventory()['duplicate_name_groups'],
      t.inventory()['duplicate_name_groups'])
