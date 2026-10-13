"""v1.11.0 中央校验 + 入库合并脚本 (level1-3 大幅夯实).

输入: imports/level123_20261014/{algebra,foundations,analysis,geometry,
      probability,discrete,computing}.json (7 批, 无 id)
处理: 字段校验(含文本长度) -> 批内去重 -> 跨批/对现有去重 -> prereq 解析
      -> 按 level 分配 id (LV1xxxx/LV2xxxx/LV3xxxx)
输出: 写回 math_mcts/data/knowledge.json, meta.version -> 1.11.0
"""
import json
import re
import shutil
from collections import Counter

REPO = '/home/hatch/workspace/math-mcts-knowledge-tree'
BAL = REPO + '/imports/level123_20261014'
BATCHES = [
    'algebra.json', 'foundations.json', 'analysis.json', 'geometry.json',
    'probability.json', 'discrete.json', 'computing.json',
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
    s = re.sub(r'（[^）]*）', '', s)
    s = re.sub(r'\([^)]*\)', '', s)
    return s.replace(' ', '').replace('　', '')


def main():
    # 备份
    shutil.copy(REPO + '/math_mcts/data/knowledge.json',
                '/tmp/knowledge_backup_20261014_lv123.json')
    tree = json.load(open(REPO + '/math_mcts/data/knowledge.json'))
    existing = tree['concepts']
    idset = {c['id'] for c in existing}
    cn2id = {c['cn']: c['id'] for c in existing}
    cn2level = {}
    for c in existing:
        # 同名多 level 并存时记最低 level（最入门的版本），用于去重判定
        if c['cn'] not in cn2level or c['level'] < cn2level[c['cn']]:
            cn2level[c['cn']] = c['level']
    en2id = {c['en'].lower(): c['id'] for c in existing if c.get('en')}

    new_cn2id = {}
    remap = {}
    all_new = []
    total_in, total_drop = 0, 0
    lv_counter = {1: 0, 2: 0, 3: 0}

    for fname in BATCHES:
        raw = json.load(open(f'{BAL}/{fname}'))
        total_in += len(raw)
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
                assert 1 <= lv <= 3, 'level 必须 1-3'
                r['level'] = lv
            except Exception:
                errs.append(f"bad level {r.get('level')}")
            if r.get('kind') == '思路' and not (r.get('example') or '').strip():
                errs.append('思路 missing example')
            if not isinstance(r.get('formulas', []), list):
                errs.append('formulas not list')
            if len(r.get('formulas', [])) > 3:
                errs.append('formulas > 3')
            # 文本长度红线
            dl, el = len(r.get('definition') or ''), len(r.get('example') or '')
            if dl > 100:
                errs.append(f'definition {dl}字超限')
            elif dl > 80:
                note(f'WARN {fname}#{i} "{r.get("cn")}" definition {dl}字(>80, 保留待修)')
            if el > 80:
                errs.append(f'example {el}字超限')
            elif el > 60:
                note(f'WARN {fname}#{i} "{r.get("cn")}" example {el}字(>60, 保留待修)')
            t = r.get('tags') or []
            if not any(x in ('核心', '重要') for x in t):
                errs.append(f'tags 非重要 {t}')
            r.setdefault('example', '')
            r.setdefault('formulas', [])
            r.setdefault('prereq_names', [])
            if errs:
                note(f'DROP {fname}#{i} {r.get("cn")}: {errs}')
                total_drop += 1
                continue
            valid.append(r)
        # 批内去重
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
                grp.sort(key=lambda g: (g['level'], -len(g['definition'])))
                deduped.append(grp[0])
                note(f'DEDUP-intra {fname} "{cn}" x{len(grp)}')
                total_drop += len(grp) - 1
            else:
                deduped.extend(grp)
                note(f'KEEP-cross-branch {fname} "{cn}" x{len(grp)}')
        # 对现有库去重：同名且 level 接近(<=1)视为真重复；若新条目比库内
        # 最入门版本还低至少 2 级，则保留为"入门版"(夯实 level1-3 的目标)
        kept = []
        for r in deduped:
            if r['cn'] in cn2id:
                gap = cn2level[r['cn']] - r['level']
                if gap >= 2:
                    note(f'KEEP-level-diff {fname} "{r["cn"]}" '
                         f'new L{r["level"]} vs existing L{cn2level[r["cn"]]}')
                else:
                    note(f'DROP-exists-cn {fname} "{r["cn"]}"')
                    remap[r['cn']] = cn2id[r['cn']]
                    total_drop += 1
                    continue
            if (r.get('en') or '').lower() in en2id:
                note(f'DROP-exists-en {fname} "{r["cn"]}"')
                remap[r['cn']] = en2id[(r.get('en') or '').lower()]
                total_drop += 1
                continue
            if r['cn'] in new_cn2id:
                note(f'DROP-cross-batch {fname} "{r["cn"]}"')
                remap[r['cn']] = new_cn2id[r['cn']]
                total_drop += 1
                continue
            kept.append(r)
        # 按 level 分配 id
        for r in kept:
            lv = r['level']
            lv_counter[lv] += 1
            nid = f'LV{lv}{lv_counter[lv]:04d}'
            assert nid not in idset, f'id collision {nid}'
            idset.add(nid)
            r['_nid'] = nid
            new_cn2id[r['cn']] = nid
        all_new.extend([(fname, r) for r in kept])
        print(f'{fname}: in={len(raw)} kept={len(kept)}', flush=True)

    # prereq 解析
    batch_cn = {r['cn']: r['_nid'] for _, r in all_new}
    norm_map = {}
    for cn, nid in batch_cn.items():
        norm_map.setdefault(norm(cn), nid)
    for cn, nid in cn2id.items():
        norm_map.setdefault(norm(cn), nid)
    unresolved = Counter()
    for fname, r in all_new:
        pids = []
        for name in r.get('prereq_names', []):
            if name.startswith('NEW:'):
                cn = name[4:]
                nid = (batch_cn.get(cn) or remap.get(cn) or cn2id.get(cn)
                       or norm_map.get(norm(cn)))
                if nid and nid != r['_nid']:
                    pids.append(nid)
                else:
                    unresolved[f'{fname}:NEW:{cn}'] += 1
            else:
                nid = cn2id.get(name) or new_cn2id.get(name) or remap.get(name)
                if nid and nid != r['_nid']:
                    pids.append(nid)
                else:
                    unresolved[f'{fname}:{name}'] += 1
        seen = set()
        r['prereq'] = [p for p in pids if not (p in seen or seen.add(p))]

    final = []
    for fname, r in all_new:
        e = {k: r.get(k) for k in SCHEMA_KEYS if k != 'id'}
        e['id'] = r['_nid']
        e['prereq'] = r['prereq']
        final.append(e)

    tree['concepts'].extend(final)
    tree['meta']['version'] = '1.11.0'
    json.dump(tree, open(REPO + '/math_mcts/data/knowledge.json', 'w'),
              ensure_ascii=False)
    open(BAL + '/merge.log', 'w').write('\n'.join(log) + '\n')

    print(f'== merged {len(final)} new, dropped {total_drop}, '
          f'total now {len(tree["concepts"])} ==')
    print(f'LV1={lv_counter[1]} LV2={lv_counter[2]} LV3={lv_counter[3]}')
    print(f'unresolved prereq refs: {sum(unresolved.values())} '
          f'({len(unresolved)} distinct)')
    for k, v in unresolved.most_common(10):
        print('  ', k, v)
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
