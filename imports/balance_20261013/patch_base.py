"""v1.7.0 补丁: 补 10 个缺失的基础概念 + 修复 22 条悬空 prereq 引用."""
import json

REPO = '/home/hatch/workspace/math-mcts-knowledge-tree'
BAL = REPO + '/imports/balance_20261013'

NEW_CONCEPTS = [
    dict(cn='紧集', en='Compact Set',
         definition='每个开覆盖都有有限子覆盖的集合；直观说就是"有界闭集"在一般拓扑空间中的推广。',
         domain_cn='几何与拓扑', domain_en='Geometry & Topology',
         branch_cn='点集拓扑', topic_cn='紧性', level=2, kind='概念',
         example='闭区间 [0,1] 是紧集；紧集上的连续函数必取到最大值最小值。',
         formulas=[], tags=['核心'], prereq=[]),
    dict(cn='Riemann 积分', en='Riemann Integral',
         definition='用小区间的"高×宽"逼近曲边梯形面积的积分；大一微积分学的就是它。',
         domain_cn='分析', domain_en='Analysis',
         branch_cn='实分析', topic_cn='积分理论', level=2, kind='概念',
         example='∫₀¹ x² dx = 1/3 就是 Riemann 积分的计算。',
         formulas=['∫ₐᵇ f = lim Σ f(ξᵢ)Δxᵢ'], tags=['核心'], prereq=[]),
    dict(cn='概率的定义', en='Definition of Probability',
         definition='Kolmogorov 公理化：概率是样本空间上满足非负性、规范性、可列可加性的测度。',
         domain_cn='概率与统计', domain_en='Probability & Statistics',
         branch_cn='随机变量与分布', topic_cn='概率基础', level=1, kind='概念',
         example='掷骰子出现偶数的概率 = 3/6 = 1/2，背后就是这三条公理。',
         formulas=['P(Ω)=1', 'P(∪Aᵢ)=ΣP(Aᵢ)（互斥）'], tags=['核心'], prereq=[]),
    dict(cn='平稳过程', en='Stationary Process',
         definition='统计特性不随时间平移而变的时间序列模型；严平稳要求分布不变，宽平稳只要求均值方差与自协方差结构不变。',
         domain_cn='概率与统计', domain_en='Probability & Statistics',
         branch_cn='随机过程', topic_cn='平稳性', level=3, kind='概念',
         example='ARMA 建模第一步就是检验序列是否平稳，不平稳先差分。',
         formulas=[], tags=['重要'], prereq=[]),
    dict(cn='法向量', en='Normal Vector',
         definition='与曲面（曲线）在某点切平面（切线）垂直的向量；曲面论的起点。',
         domain_cn='几何与拓扑', domain_en='Geometry & Topology',
         branch_cn='微分几何', topic_cn='曲线曲面论', level=1, kind='概念',
         example='球面 x²+y²+z²=1 在点 (x,y,z) 的法向量就是 (x,y,z) 本身。',
         formulas=[], tags=[], prereq=[]),
    dict(cn='欧氏空间的黎曼度量', en='Riemannian Metric of Euclidean Space',
         definition='欧氏空间 Rⁿ 上的标准内积 gᵢⱼ=δᵢⱼ；一切黎曼几何的参照系和出发点。',
         domain_cn='几何与拓扑', domain_en='Geometry & Topology',
         branch_cn='黎曼几何', topic_cn='黎曼度量', level=3, kind='概念',
         example='球面的度量就是把欧氏度量"诱导"到球面上得到的。',
         formulas=['gᵢⱼ = δᵢⱼ'], tags=[], prereq=[]),
    dict(cn='罗尔定理', en="Rolle's Theorem",
         definition='闭区间连续、开区间可导、端点值相等的函数，内部必有一点导数为零。',
         domain_cn='分析', domain_en='Analysis',
         branch_cn='实分析', topic_cn='微分中值定理', level=2, kind='定理',
         example='f(a)=f(b) 则 f 在 (a,b) 内必有"水平切线"；是拉格朗日中值定理的特例之源。',
         formulas=['f(a)=f(b) ⇒ ∃ξ∈(a,b), f′(ξ)=0'], tags=['核心'],
         prereq=['AN03']),
    dict(cn='多元微积分', en='Multivariable Calculus',
         definition='把极限、微分、积分推广到多元函数的理论：偏导数、梯度、重积分、线面积分。',
         domain_cn='分析', domain_en='Analysis',
         branch_cn='实分析', topic_cn='多元分析', level=2, kind='概念',
         example='求山丘 z=f(x,y) 的最高点，就是多元微积分的典型问题。',
         formulas=[], tags=['核心'], prereq=[]),
    dict(cn='勒贝格积分', en='Lebesgue Integration',
         definition='按"函数值"分层求和的积分；比 Riemann 积分更强大，能处理更"破碎"的函数，是现代概率论的基础。',
         domain_cn='分析', domain_en='Analysis',
         branch_cn='实分析', topic_cn='积分理论', level=3, kind='概念',
         example='Dirichlet 函数（有理点取 1、无理点取 0）Riemann 不可积，但 Lebesgue 可积且积分为 0。',
         formulas=[], tags=['核心'], prereq=[]),
]

# 悬空引用 -> 已有条目 id 的别名映射
ALIAS = {
    '连续函数': 'AN02',
    '线性空间': 'AL08',
    '泰勒展开': 'AN19',
    '分部积分': 'AN36',
    '导数定义': 'AN03',
    '追赶法': 'B7C0028',   # Thomas 算法即追赶法, 计算批已收录
}


def main():
    tree = json.load(open(REPO + '/math_mcts/data/knowledge.json'))
    idset = {c['id'] for c in tree['concepts']}
    cn2id = {c['cn']: c['id'] for c in tree['concepts']}
    en2id = {c['en'].lower(): c['id'] for c in tree['concepts'] if c.get('en')}
    assert not (set(ALIAS) & set(cn2id)), 'alias target missing?'
    for tgt in ALIAS.values():
        assert tgt in idset, f'alias target id missing: {tgt}'

    added = []
    for i, r in enumerate(NEW_CONCEPTS, 1):
        nid = f'B7Z{i:04d}'
        assert nid not in idset, nid
        assert r['cn'] not in cn2id, r['cn']
        assert r['en'].lower() not in en2id, r['en']
        idset.add(nid)
        e = dict(id=nid, prereq=r.pop('prereq'), tags=r.pop('tags'),
                 formulas=r.pop('formulas'), **r)
        # 字段顺序与其它条目一致
        e = {k: e.get(k, [] if k in ('prereq', 'tags', 'formulas') else '')
             for k in ['id', 'cn', 'en', 'definition', 'domain_cn',
                       'domain_en', 'branch_cn', 'topic_cn', 'level',
                       'prereq', 'tags', 'kind', 'example', 'formulas']}
        tree['concepts'].append(e)
        cn2id[r['cn']] = nid
        added.append((nid, r['cn']))

    # 修复 22 条悬空引用
    det = json.load(open(BAL + '/unresolved.json'))
    fixed = 0
    by_id = {c['id']: c for c in tree['concepts']}
    alias_new = {cn: nid for nid, cn in added}
    for u in det:
        ref = u['ref']
        nid = alias_new.get(ref) or ALIAS.get(ref)
        if not nid:
            print('STILL UNRESOLVED:', u)
            continue
        c = by_id[u['entry_id']]
        if nid not in c['prereq']:
            c['prereq'].append(nid)
            fixed += 1

    json.dump(tree, open(REPO + '/math_mcts/data/knowledge.json', 'w'),
              ensure_ascii=False)
    print(f'added {len(added)} concepts, fixed {fixed} prereq refs')
    for nid, cn in added:
        print(' ', nid, cn)


if __name__ == '__main__':
    main()
