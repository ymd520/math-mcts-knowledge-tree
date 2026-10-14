"""Build reproducible editorial packs; no theorem-proving or raw-source scraping.

Existing IDs are preserved. Exact normalized Chinese-name matches are enriched
in place; uncertain semantic synonyms are not automatically merged.
"""
from __future__ import annotations
import hashlib
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from math_mcts.catalog import name_key

SOURCES = {
    "PRE": ("OpenStax, Prealgebra 2e", "https://openstax.org/books/prealgebra-2e/pages/1-introduction"),
    "ALG": ("OpenStax, College Algebra 2e", "https://openstax.org/books/college-algebra-2e/pages/1-introduction-to-prerequisites"),
    "RA": ("Jiří Lebl, Basic Analysis I & II", "https://www.jirka.org/ra/"),
    "DIS": ("Oscar Levin, Discrete Mathematics: An Open Introduction", "https://discrete.openmathbooks.org/"),
    "PRO": ("Hossein Pishro-Nik, Introduction to Probability, Statistics, and Random Processes", "https://www.probabilitycourse.com/"),
    "LIN": ("Jim Hefferon, Linear Algebra", "https://hefferon.net/linearalgebra/"),
    "NUM": ("Steven G. Johnson, MIT 18.335 Numerical Methods", "https://math.mit.edu/~stevenj/18.335/"),
    "AATA": ("Thomas W. Judson, Abstract Algebra: Theory and Applications", "https://judsonbooks.org/abstract-algebra-theory-and-applications/"),
    "MEAS": ("Terence Tao, An Introduction to Measure Theory", "https://terrytao.wordpress.com/books/an-introduction-to-measure-theory/"),
    "OPT": ("Stephen Boyd and Lieven Vandenberghe, Convex Optimization", "https://web.stanford.edu/~boyd/cvxbook/"),
}
DOMAINS = {"代数": "Algebra", "分析": "Analysis", "数学基础": "Foundations",
           "几何与拓扑": "Geometry & Topology", "概率与统计": "Probability & Statistics",
           "离散数学": "Discrete Math", "计算与优化": "Computing & Optimization"}

REGRADE = {
    "可测空间": 3, "概率测度": 3, "测度空间": 3, "零测集": 3, "几乎处处": 3,
    "次可数可加性": 3, "测度的单调性": 3, "开集的 Lebesgue 测度": 3,
    "简单函数的标准表示": 3, "连续函数皆可测": 3, "可测函数的正部与负部": 3,
    "几乎处处相等的函数": 3, "几乎处处收敛": 3, "简单函数的积分": 3,
    "零测集不影响积分": 3, "Lebesgue 积分的几何意义": 3,
    "子空间拓扑": 3, "离散拓扑": 3, "平凡拓扑": 3, "拓扑和": 4,
    "可测函数": 3, "勒贝格积分": 4, "Riemann 积分": 2,
}

# Explicitly inspected synonymous statements; no fuzzy automatic semantic merge.
CANONICAL = {
    "空真命题": "B7F0127", "中位数定义": "B7P0030",
    "多项式因式定理": "AL50", "导数链式法则": "AN30",
    "有限集合加法原理": "B7D0001", "有限集合乘法原理": "B7D0002",
    "二项系数总和": "B7D0011", "鸽巢原理基础版": "DM02",
    "二项式定理有限版": "B7D0013", "条件概率定义": "PR02",
    "期望线性性": "B7P0120", "正项级数比较判别": "AN44",
    "紧域连续函数取极值": "B7G0062", "连续函数介值性": "AN197",
    "拉格朗日中值定理": "AN04", "罗尔定理完整条件": "B7Z0007",
    "概率并集上界": "B7P0234", "全期望公式": "B7P0161",
    "群类方程": "AL90", "魏尔斯特拉斯M判别": "AN69",
    "弱对偶性": "B7C0296", "最大流最小割": "DM90",
    "整数非负分拆星棒法": "B7D0019", "单射函数定义": "B7F0025",
    "满射函数定义": "B7F0026", "双射与逆映射": "B7F0027",
    "马尔可夫不等式": "PR161", "实数柯西判据": "AN66",
    "闭有界欧氏紧性": "AN63", "巴拿赫压缩映射定理": "AN161",
    "轨道稳定子公式": "AL87", "凯莱哈密顿代入": "AL33",
    "正规复矩阵谱定理": "AL79", "最优低秩逼近": "B7C0008",
    "法图引理": "B7A0079", "托内利非负换序": "B7A0152",
    "富比尼绝对可积换序": "B7A0153", "闵可夫斯基不等式": "B7A0099",
    "赫尔德不等式": "B7A0098", "霍夫丁有界和尾界": "PR165",
    "经典中心极限定理": "PR10", "第一BorelCantelli引理": "B7A0082",
    "独立第二BorelCantelli引理": "B7A0083", "Jensen期望不等式": "PR163",
    "凸投影非扩张": "B7C0348", "对称正定Cholesky分解": "B7C0003",
    "Hall匹配条件": "DM22", "二部图匹配顶点覆盖": "B7D0243",
    "Cayley标号树计数": "DM85", "Burnside轨道计数": "DM26",
    "组合数Vandermonde恒等式": "DM44", "错排容斥公式": "DM35",
    "Slater强对偶条件": "B7C0302",
}


def digest(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build():
    base = json.loads((ROOT / "math_mcts/data/knowledge.json").read_text(encoding="utf-8"))
    originals = {r["id"]: r for r in base["concepts"]}
    names = {}
    for row in base["concepts"]:
        names.setdefault(name_key(row["cn"]), []).append(row["id"])
    refs = Counter(p for c in originals.values() for p in c.get("prereq", []))
    changes = {}
    structural = []
    for cid, row in originals.items():
        if row["level"] <= 4 and refs[cid] >= 2 and not {"核心", "重要"} & set(row.get("tags", [])):
            changes[cid] = {"tags": ["重要", *row.get("tags", [])],
                            "importance_reason": f"被{refs[cid]}条现有知识明确列为前置：依赖结构重要性，不代表内容已经核验"}
            structural.append(cid)
        target = REGRADE.get(row["cn"])
        if target and target != row["level"]:
            changes.setdefault(cid, {}).update({"level": target,
                "level_status": "editorial_regrade_20261014",
                "original_metadata": {**row.get("original_metadata", {}),
                                      "previous_level": row["level"],
                                      "level_reason": "按初中、高中、大学基础、大学进阶、研究生统一难度；未改变定理结论"}})

    added = []
    authored = []
    duplicate_inputs = set()
    group = None
    for line in (ROOT / "math_mcts/data/curated_seed_20261014.txt").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            group = line[1:].split("|")
            continue
        cn, en, assumptions, conclusion, formula = line.split("|")
        if name_key(cn) in duplicate_inputs:
            raise ValueError("Duplicate authored title: " + cn)
        duplicate_inputs.add(name_key(cn))
        level, domain, branch, source, locator = group
        level = int(level)
        # Linear operator statements are referenced to linear algebra, not group theory.
        if domain == "代数" and level == 4 and any(t in cn for t in ["矩阵", "算子", "多项式判据", "凯莱", "奇异值", "低秩"]):
            source = "LIN"
        source_title, url = SOURCES[source]
        known = names.get(name_key(cn), [])
        if not known and cn in CANONICAL:
            known = [CANONICAL[cn]]
        cid = known[0] if known else f"C14L{level}_" + hashlib.sha256(name_key(cn).encode()).hexdigest()[:12]
        if not known and cid in originals:
            raise ValueError("New stable ID collides with base")
        authored.append({"id": cid, "title": cn, "level": level, "action": "enriched" if known else "added"})
        fields = {"definition": assumptions + "；" + conclusion, "assumptions": assumptions,
                  "conclusion": conclusion, "formulas": [formula], "level": level,
                  "tags": ["重要", "教材基础"], "source_url": url,
                  "source_locator": source_title + " / " + locator + "（主题参考，非逐条定位核验）",
                  "verification_status": "editorial_statement_review_not_formal",
                  "curation_status": "editorial_curated_20261014",
                  "level_status": "education_stage_rubric_20261014",
                  "importance_reason": "标准课程中的定义、计算规则、基础定理或必要条件，供跨领域推导使用",
                  "statement_sha256": hashlib.sha256((assumptions + "\n" + conclusion + "\n" + formula).encode()).hexdigest(),
                  "reference_relation": "topic_reference_not_statement_certification"}
        if known:
            old = originals[cid]
            fields["tags"] = list(dict.fromkeys(["重要", *old.get("tags", []), "教材基础"]))
            fields["aliases"] = list(dict.fromkeys([*old.get("aliases", []), cn, en]))
            changes.setdefault(cid, {}).update(fields)
        else:
            prereq = []
            if domain == "分析" and level >= 2:
                prereq.append("AN01")
            if domain == "代数" and level >= 3:
                prereq.append("AL05" if source == "LIN" else "AL13")
            if domain == "概率与统计" and level >= 2:
                prereq.append("PR01")
            if domain == "离散数学" and level >= 2:
                prereq.append("BS01")
            if branch == "度量与拓扑":
                prereq.append("GE167")
            if source == "MEAS":
                prereq.append("B7A0005")
            if cn.startswith("向量"):
                prereq.append("AL04")
            kind = "概念" if any(w in cn for w in ("定义", "区别", "风险", "解释", "误差")) else ("公式" if level <= 2 else "定理")
            fields.update({"id": cid, "cn": cn, "en": en, "domain_cn": domain,
                           "domain_en": DOMAINS[domain], "branch_cn": branch, "topic_cn": locator,
                           "kind": kind, "prereq": list(dict.fromkeys(prereq)),
                           "prereq_status": "partial_curricular_dependencies_not_formal_hypotheses",
                           "example": "用途：" + locator + "中的计算、条件检查与推导"})
            added.append(fields)

    out = ROOT / "math_mcts/data/curated"
    out.mkdir(exist_ok=True)
    manifest = {"version": "1.10.0", "packs": [],
                "source_seed_sha256": hashlib.sha256((ROOT / "math_mcts/data/curated_seed_20261014.txt").read_bytes()).hexdigest(),
                "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "base_snapshot_sha256": hashlib.sha256((ROOT / "math_mcts/data/knowledge.json").read_bytes()).hexdigest()}
    for level in range(1, 5):
        pack_rows = [r for r in added if r["level"] == level]
        overlays = [{"id": cid, "base_sha256": digest(originals[cid]), "changes": patch}
                    for cid, patch in sorted(changes.items())
                    if patch.get("level", originals[cid]["level"]) == level]
        pack = {"concepts": pack_rows, "overlays": overlays}
        filename = f"level_{level}_20261014.json.gz"
        encoded = (json.dumps(pack, ensure_ascii=False, indent=2) + "\n").encode()
        (out / filename).write_bytes(gzip.compress(encoded, mtime=0))
        old_uncompressed = out / f"level_{level}_20261014.json"
        if old_uncompressed.exists():
            old_uncompressed.unlink()
        manifest["packs"].append({"file": filename, "count": len(pack_rows),
                                  "overlays": len(overlays),
                                  "sha256": hashlib.sha256((out / filename).read_bytes()).hexdigest()})
    # The deep Level 1–3 pack is a separately authored reviewed-conditions
    # extension, not part of the historic curated_seed input. Retain it when
    # rebuilding the legacy packs; never silently drop 105 sourced records.
    extension = out / "level123_multidomain_20261014.json"
    if extension.exists():
        extension_data = extension.read_bytes()
        extension_records = json.loads(extension_data)
        if len(extension_records.get("concepts", [])) != 105:
            raise ValueError("Unexpected Level 1–3 extension count")
        if extension_records.get("overlays", []) != []:
            raise ValueError("Level 1–3 extension must not override older records")
        manifest["packs"].append({
            "file": extension.name,
            "count": len(extension_records["concepts"]),
            "overlays": 0,
            "sha256": hashlib.sha256(extension_data).hexdigest(),
        })
        manifest["version"] = "1.13.0"
    write_json(out / "manifest.json", manifest)
    report = {"base_count": len(originals), "authored_statements": len(authored),
              "added": len(added), "authored_enrichments": sum(r["action"] == "enriched" for r in authored),
              "dependency_priority_updates": len(structural),
              "editorial_overlays": len(changes), "authored_levels": dict(Counter(r["level"] for r in authored)),
              "level_rubric": {1: "初中基础", 2: "高中与微积分入门", 3: "大学基础", 4: "大学进阶", 5: "研究生与前沿"},
              "source_relation": "originally worded mathematical facts; URLs are topic references, not line-by-line proof certification",
              "authored": authored, "structural_priority_ids": structural}
    write_json(out / "build_report.json", report)
    return report


if __name__ == "__main__":
    r = build()
    print(json.dumps({k:v for k,v in r.items() if k not in {"authored", "structural_priority_ids"}}, ensure_ascii=False))
