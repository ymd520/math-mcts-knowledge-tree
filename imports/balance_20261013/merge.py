"""v1.7.0 中央校验 + 入库合并脚本.

输入: imports/balance_20261013/{foundations,probability,analysis,
      geometry_topology,computing,discrete}.json (6 批, 无 id)
处理: 字段校验 -> 批内去重 -> 跨批/对现有去重 -> prereq 解析 -> 分配 id
输出: 写回 math_mcts/data/knowledge.json, meta.version -> 1.7.0
"""
import json
import re
import sys
from collections import Counter

REPO = '/home/hatch/workspace/math-mcts-knowledge-tree'
BAL = REPO + '/imports/balance_20261013'
BATCHES = [
    ('foundations.json', 'B7F'),
    ('probability.json', 'B7P'),
    ('analysis.json', 'B7A'),
    ('geometry_topology.json', 'B7G'),
    ('computing.json', 'B7C'),
    ('discrete.json', 'B7D'),
]
ALLOWED_KINDS = {'概念', '定理', '推论', '思路', '公式', '算法',
                 '分布', '方法', '引理', '检验'}
SCHEMA_KEYS = ['id', 'cn', 'en', 'definition', 'domain_cn', 'domain_en',
               'branch_cn', 'topic_cn', 'level', 'prereq', 'tags', 'kind',
               'example', 'formulas']

log = []


def note(msg):
    log.append(msg)


def norm(s):
    """归一化中文名: 去括号注释、去空格, 用于模糊匹配 prereq 引用."""
    s = re.sub(r'（[^）]*）', '', s)
    s = re.sub(r'\([^)]*\)', '', s)
    return s.replace(' ', '').replace('　', '')


def main():
    tree = json.load(open(REPO + '/math_mcts/data/knowledge.json'))
    existing = tree['concepts']
    idset = {c['id'] for c in existing}
    cn2id = {c['cn']: c['id'] for c in existing}
    en2id = {c['en'].lower(): c['id'] for c in existing if c.get('en')}

    new_cn2id = {}   # 跨批去重: cn -> 新 id
    remap = {}       # 被去重掉的 cn -> 存活者 id (prereq 重定向用)
    all_new = []     # 最终入库条目(未分配 id 前为 dict)
    total_in, total_drop = 0, 0

    for fname, prefix in BATCHES:
        raw = json.load(open(f'{BAL}/{fname}'))
        total_in += len(raw)
        # ---- 字段校验 ----
        valid = []
        for i, r in enumerate(raw):
            errs = []
            for k in ['cn', 'en', 'definition', 'domain_cn', 'domain_en',
                      'branch_cn', 'topic_cn', 'level', 'kind']:
                if k not in r or r[k] in (None, ''):
                    errs.append(f'missing {k}')
            if r.get('kind') not in ALLOWED_KINDS:
                errs.append(f"bad kind {r.get('kind')}")
            try:
                lv = int(r.get('level', 0))
                assert 1 <= lv <= 5
                r['level'] = lv
            except Exception:
                errs.append(f"bad level {r.get('level')}")
            if r.get('kind') == '思路' and not (r.get('example') or '').strip():
                errs.append('思路 missing example')
            if not isinstance(r.get('formulas', []), list):
                errs.append('formulas not list')
            r.setdefault('tags', [])
            r.setdefault('example', '')
            r.setdefault('formulas', [])
            r.setdefault('prereq_names', [])
            if errs:
                note(f'DROP {fname}#{i} {r.get("cn")}: {errs}')
                total_drop += 1
                continue
            valid.append(r)
        # ---- 批内去重 (同 cn) ----
        by_cn = {}
        for r in valid:
            by_cn.setdefault(r['cn'], []).append(r)
        deduped = []
        for cn, grp in by_cn.items():
            if len(grp) == 1:
                deduped.append(grp[0])
                continue
            branches = {g['branch_cn'] for g in grp}
            if len(branches) == 1:
                # 同分支真重复: 留 level 低、定义长的
                grp.sort(key=lambda g: (g['level'], -len(g['definition'])))
                deduped.append(grp[0])
                note(f'DEDUP-intra {fname} "{cn}" x{len(grp)} -> keep L{grp[0]["level"]} '
                     f'{grp[0]["branch_cn"]}')
                total_drop += len(grp) - 1
            else:
                # 跨分支同名: 可能是同名不同定理, 保留并标注
                deduped.extend(grp)
                note(f'KEEP-cross-branch {fname} "{cn}" x{len(grp)} '
                     f'branches={sorted(branches)}')
        # ---- 对现有库去重 ----
        kept = []
        for r in deduped:
            if r['cn'] in cn2id:
                note(f'DROP-exists-cn {fname} "{r["cn"]}" (id {cn2id[r["cn"]]})')
                remap[r['cn']] = cn2id[r['cn']]
                total_drop += 1
                continue
            if (r.get('en') or '').lower() in en2id:
                note(f'DROP-exists-en {fname} "{r["cn"]}" en={r["en"]}')
                remap[r['cn']] = en2id[(r.get('en') or '').lower()]
                total_drop += 1
                continue
            if r['cn'] in new_cn2id:
                note(f'DROP-cross-batch {fname} "{r["cn"]}" dup of {new_cn2id[r["cn"]]}')
                remap[r['cn']] = new_cn2id[r['cn']]
                total_drop += 1
                continue
            kept.append(r)
        # ---- 分配 id ----
        for j, r in enumerate(kept, 1):
            nid = f'{prefix}{j:04d}'
            assert nid not in idset, f'id collision {nid}'
            idset.add(nid)
            r['_nid'] = nid
            new_cn2id[r['cn']] = nid
        all_new.extend([(fname, r) for r in kept])
        print(f'{fname}: in={len(raw)} kept={len(kept)}', flush=True)

    # ---- prereq 解析 ----
    batch_cn = {r['cn']: r['_nid'] for _, r in all_new}
    # 模糊匹配表: 归一化名 -> id (批内优先, 其次现有库)
    norm_map = {}
    for cn, nid in batch_cn.items():
        norm_map.setdefault(norm(cn), nid)
    for cn, nid in cn2id.items():
        norm_map.setdefault(norm(cn), nid)
    unresolved = Counter()
    rescued = Counter()
    for fname, r in all_new:
        pids = []
        for name in r.get('prereq_names', []):
            if name.startswith('NEW:'):
                cn = name[4:]
                nid = (batch_cn.get(cn) or remap.get(cn) or cn2id.get(cn)
                       or norm_map.get(norm(cn)))
                if nid and nid != r['_nid']:
                    pids.append(nid)
                    if nid != batch_cn.get(cn):
                        rescued[f'{fname}:NEW:{cn}'] += 1
                else:
                    unresolved[f'{fname}:NEW:{cn}'] += 1
            else:
                nid = (cn2id.get(name) or new_cn2id.get(name)
                       or remap.get(name))
                if nid and nid != r['_nid']:
                    pids.append(nid)
                else:
                    unresolved[f'{fname}:{name}'] += 1
        # 去重保序
        seen = set()
        r['prereq'] = [p for p in pids if not (p in seen or seen.add(p))]

    # ---- 组装入库 ----
    final = []
    for fname, r in all_new:
        e = {k: r.get(k) for k in SCHEMA_KEYS if k != 'id'}
        e['id'] = r['_nid']
        e['prereq'] = r['prereq']
        final.append(e)

    tree['concepts'].extend(final)
    tree['meta']['version'] = '1.7.0'
    json.dump(tree, open(REPO + '/math_mcts/data/knowledge.json', 'w'),
              ensure_ascii=False)
    open(BAL + '/merge.log', 'w').write('\n'.join(log) + '\n')

    print(f'== merged {len(final)} new, dropped {total_drop}, '
          f'total now {len(tree["concepts"])} ==')
    print(f'unresolved prereq refs: {sum(unresolved.values())} '
          f'({len(unresolved)} distinct), rescued by fuzzy match: '
          f'{sum(rescued.values())}')
    for k, v in unresolved.most_common(10):
        print('  ', k, v)
    # 落盘未解析引用明细, 供补丁脚本使用: [{entry_cn, entry_id, ref}]
    det = []
    for fname, r in all_new:
        for name in r.get('prereq_names', []):
            key = name[4:] if name.startswith('NEW:') else name
            ukey = f'{fname}:{"NEW:" if name.startswith("NEW:") else ""}{key}'
            if ukey in unresolved:
                det.append({'entry_cn': r['cn'], 'entry_id': r['_nid'],
                            'ref': key, 'is_new': name.startswith('NEW:')})
    json.dump(det, open(BAL + '/unresolved.json', 'w'), ensure_ascii=False)


if __name__ == '__main__':
    main()
