"""v1.11.0 补丁: 补 8 个缺失的 L1 基础概念 + 别名映射, 修复 30 条悬空 prereq."""
import json
import shutil

REPO = '/home/hatch/workspace/math-mcts-knowledge-tree'
P = REPO + '/math_mcts/data/knowledge.json'
shutil.copy(P, '/tmp/knowledge_backup_20261014_lv123_patch.json')
tree = json.load(open(P))
by_id = {c['id']: c for c in tree['concepts']}
idset = set(by_id)

# 别名映射: 引用名 -> 已有 id
ALIAS = {
    '映射': 'BS05',      # 映射(函数)
    '函数': 'BS05',      # 映射(函数)即函数概念
    '量词': 'BS11',      # 量词(∀∃)
}

# 新增 8 个 L1 基础概念 (id 段 LV1 继续编号)
NEW = [
    dict(cn='等腰三角形底角', en='Base Angles of Isosceles Triangle',
         definition='等腰三角形两底角相等；反之两角相等的三角形是等腰三角形。',
         domain_cn='几何与拓扑', domain_en='Geometry and Topology',
         branch_cn='平面几何', topic_cn='三角形', level=1, kind='定理',
         tags=['重要'], formulas=['∠B = ∠C（AB = AC）'], example='顶角 40° 的等腰三角形，底角各 70°。',
         prereq_names=[]),
    dict(cn='菱形对角线面积', en='Area of Rhombus via Diagonals',
         definition='菱形面积等于两条对角线乘积的一半。',
         domain_cn='几何与拓扑', domain_en='Geometry and Topology',
         branch_cn='平面几何', topic_cn='四边形', level=1, kind='公式',
         tags=['重要'], formulas=['S = d₁d₂/2'], example='对角线 6 和 8 的菱形面积为 24。',
         prereq_names=[]),
    dict(cn='圆的直径与半径', en='Diameter and Radius',
         definition='同圆中直径是半径的两倍：d = 2r。',
         domain_cn='几何与拓扑', domain_en='Geometry and Topology',
         branch_cn='平面几何', topic_cn='圆', level=1, kind='公式',
         tags=['核心'], formulas=['d = 2r'], example='半径 5 的圆直径为 10。',
         prereq_names=[]),
    dict(cn='圆切线垂直半径', en='Tangent Perpendicular to Radius',
         definition='圆的切线垂直于过切点的半径。',
         domain_cn='几何与拓扑', domain_en='Geometry and Topology',
         branch_cn='平面几何', topic_cn='圆', level=1, kind='定理',
         tags=['核心'], formulas=[], example='过切点作切线，它与该半径成 90°。',
         prereq_names=['圆的直径与半径']),
    dict(cn='二维两点距离', en='Distance Between Two Points',
         definition='平面上两点距离为横纵坐标差平方和的算术平方根。',
         domain_cn='几何与拓扑', domain_en='Geometry and Topology',
         branch_cn='解析几何', topic_cn='坐标', level=1, kind='公式',
         tags=['核心'], formulas=['d = √((x₂−x₁)² + (y₂−y₁)²)'],
         example='(0,0) 到 (3,4) 的距离为 5。', prereq_names=[]),
    dict(cn='直线斜率', en='Slope of a Line',
         definition='直线斜率 k = 纵坐标增量/横坐标增量，刻画倾斜程度。',
         domain_cn='几何与拓扑', domain_en='Geometry and Topology',
         branch_cn='解析几何', topic_cn='直线', level=1, kind='概念',
         tags=['核心'], formulas=['k = Δy/Δx = tanθ'],
         example='y = 2x + 1 的斜率为 2。', prereq_names=[]),
    dict(cn='三角形面积', en='Area of Triangle',
         definition='三角形面积等于底乘高的一半。',
         domain_cn='几何与拓扑', domain_en='Geometry and Topology',
         branch_cn='平面几何', topic_cn='三角形', level=1, kind='公式',
         tags=['核心'], formulas=['S = bh/2'], example='底 6 高 4 的三角形面积为 12。',
         prereq_names=[]),
    dict(cn='直角三角形锐角和', en='Acute Angles of Right Triangle',
         definition='直角三角形的两个锐角互余，和为 90°。',
         domain_cn='几何与拓扑', domain_en='Geometry and Topology',
         branch_cn='平面几何', topic_cn='三角形', level=1, kind='定理',
         tags=['重要'], formulas=['∠A + ∠B = 90°（∠C = 90°）'],
         example='一个锐角 35°，另一个为 55°。', prereq_names=[]),
    dict(cn='长方体体积', en='Volume of Cuboid',
         definition='长方体体积等于长宽高三者之乘积。',
         domain_cn='几何与拓扑', domain_en='Geometry and Topology',
         branch_cn='立体几何', topic_cn='体积', level=1, kind='公式',
         tags=['重要'], formulas=['V = abc'],
         example='3×4×5 的长方体体积为 60。', prereq_names=[]),
    dict(cn='扇形面积', en='Area of Sector',
         definition='扇形面积等于圆心角占 360° 的比例乘以圆面积。',
         domain_cn='几何与拓扑', domain_en='Geometry and Topology',
         branch_cn='平面几何', topic_cn='圆', level=1, kind='公式',
         tags=['重要'], formulas=['S = θ/360°·πr² = ½lr'],
         example='90° 扇形面积是同半径圆的四分之一。', prereq_names=[]),
    dict(cn='圆柱侧面积', en='Lateral Area of Cylinder',
         definition='圆柱侧面积等于底面周长乘以高。',
         domain_cn='几何与拓扑', domain_en='Geometry and Topology',
         branch_cn='立体几何', topic_cn='表面积', level=1, kind='公式',
         tags=['重要'], formulas=['S侧 = 2πrh'],
         example='底半径 2、高 5 的圆柱侧面积为 20π。', prereq_names=[]),
    dict(cn='直线点斜式', en='Point-Slope Form',
         definition='过点 (x₀,y₀)、斜率为 k 的直线方程为 y − y₀ = k(x − x₀)。',
         domain_cn='几何与拓扑', domain_en='Geometry and Topology',
         branch_cn='解析几何', topic_cn='直线', level=1, kind='公式',
         tags=['重要'], formulas=['y − y₀ = k(x − x₀)'],
         example='过 (1,2)、斜率 3 的直线：y − 2 = 3(x − 1)。',
         prereq_names=['直线斜率']),
    dict(cn='矩形面积', en='Area of Rectangle',
         definition='矩形面积等于长乘宽。',
         domain_cn='几何与拓扑', domain_en='Geometry and Topology',
         branch_cn='平面几何', topic_cn='四边形', level=1, kind='公式',
         tags=['核心'], formulas=['S = ab'],
         example='长 5 宽 3 的矩形面积为 15。', prereq_names=[]),
    dict(cn='角度弧度换算', en='Degree-Radian Conversion',
         definition='180° = π 弧度；角度×π/180 得弧度，弧度×180/π 得角度。',
         domain_cn='几何与拓扑', domain_en='Geometry and Topology',
         branch_cn='三角学', topic_cn='弧度制', level=1, kind='公式',
         tags=['核心'], formulas=['1° = π/180 rad，1 rad = 180°/π'],
         example='90° = π/2 弧度。', prereq_names=[]),
    dict(cn='球体积', en='Volume of Sphere',
         definition='半径 r 的球体积为 4/3 πr³。',
         domain_cn='几何与拓扑', domain_en='Geometry and Topology',
         branch_cn='立体几何', topic_cn='体积', level=1, kind='公式',
         tags=['核心'], formulas=['V = 4/3·πr³'],
         example='半径 3 的球体积为 36π。', prereq_names=[]),
]

# 现有 LV1 最大编号
mx = max(int(c['id'][3:]) for c in tree['concepts'] if c['id'].startswith('LV1'))
added = []
for i, r in enumerate(NEW, 1):
    nid = f'LV1{mx + i:04d}'
    assert nid not in idset
    idset.add(nid)
    pnames = r.pop('prereq_names')
    e = dict(r, id=nid, prereq=[])
    tree['concepts'].append(e)
    added.append((nid, r['cn']))
    print('added', nid, r['cn'])

# prereq 解析: 新增条目的 NEW 引用 + 修复悬空
cn2id = {c['cn']: c['id'] for c in tree['concepts']}
alias_new = {cn: nid for nid, cn in added}
unres = json.load(open(REPO + '/imports/level123_20261014/unresolved.json'))
fixed = 0
for u in unres:
    c = by_id.get(u['entry_id'])
    if not c:
        continue
    ref = u['ref']
    nid = ALIAS.get(ref) or alias_new.get(ref) or cn2id.get(ref)
    if nid and nid != c['id'] and nid not in c['prereq']:
        c['prereq'].append(nid)
        fixed += 1
    else:
        print('STILL UNRESOLVED:', u['entry_id'], u['entry_cn'], '<-', ref)

# 新增条目自身的 prereq (用更新后的 cn2id 查)
cn2id = {c['cn']: c['id'] for c in tree['concepts']}
by_id = {c['id']: c for c in tree['concepts']}
for nid, cn in added:
    if cn == '圆切线垂直半径':
        by_id[nid]['prereq'] = [cn2id['圆的直径与半径']]
    elif cn == '直线点斜式':
        by_id[nid]['prereq'] = [cn2id['直线斜率']]

json.dump(tree, open(P, 'w'), ensure_ascii=False)
print(f'added {len(added)}, fixed {fixed} prereq refs, total {len(tree["concepts"])}')
