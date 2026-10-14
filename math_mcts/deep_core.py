"""Authored Level 1–3 deep-core study cards; source attribution is topical only.

No imported Lean declaration is reclassified, and no generated record claims
to be a new theorem, kernel proof, or individually source-verified quotation.
The seed is versioned plaintext so review and diff are transparent.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path

SEED_PATH=Path(__file__).with_name("data")/"level123_deep.tsv"
DOMAINS={"代数":"Algebra","分析":"Analysis","数学基础":"Foundations",
         "几何与拓扑":"Geometry & Topology","概率与统计":"Probability & Statistics",
         "离散数学":"Discrete Math","计算与优化":"Computing & Optimization"}
REFERENCES={
    "ALG":("OpenStax, College Algebra 2e","https://openstax.org/details/books/college-algebra-2e"),
    "LIN":("Jim Hefferon, Linear Algebra","https://hefferon.net/linearalgebra/"),
    "AATA":("Thomas Judson, Abstract Algebra: Theory and Applications","https://judsonbooks.org/abstract-algebra-theory-and-applications/"),
    "RA":("Jiří Lebl, Basic Analysis I & II","https://www.jirka.org/ra/"),
    "DIS":("Oscar Levin, Discrete Mathematics: An Open Introduction","https://discrete.openmathbooks.org/"),
    "MIT":("MIT 6.042J, Mathematics for Computer Science","https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-spring-2015/pages/readings/"),
    "TOP":("MIT 18.901, Introduction to Topology","https://ocw.mit.edu/courses/18-901-introduction-to-topology-fall-2004/pages/lecture-notes/"),
    "PRO":("Pishro-Nik, Introduction to Probability, Statistics, and Random Processes","https://www.probabilitycourse.com/"),
    "NUM":("MIT 18.335, Introduction to Numerical Methods","https://math.mit.edu/~stevenj/18.335/"),
    "OPT":("Boyd and Vandenberghe, Convex Optimization","https://web.stanford.edu/~boyd/cvxbook/"),
}
REQUIRED_FIELDS=9


def _key(name):
    from .catalog import name_key
    return name_key(name)


def load_deep_core(*,existing_rows: list[dict], seed: Path=SEED_PATH) -> tuple[list[dict],dict]:
    known={_key(r["cn"]) for r in existing_rows}
    existing_ids={r["id"] for r in existing_rows}
    authored=[]
    group=None
    names={}
    by_level=Counter()
    by_domain=Counter()
    for lineno,line in enumerate(seed.read_text(encoding="utf-8").splitlines(),1):
        raw=line.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("@"):
            params=raw[1:].split("|")
            if len(params)!=5:
                raise ValueError(f"Bad Level 1–3 group at line {lineno}")
            level,domain,branch,topic,source=params
            level=int(level)
            if level not in (1,2,3) or domain not in DOMAINS or source not in REFERENCES:
                raise ValueError(f"Invalid Level/domain/source at line {lineno}")
            group=(level,domain,branch,topic,source)
            continue
        if group is None:
            raise ValueError(f"Knowledge entry before group at line {lineno}")
        fields=raw.split("|")
        if len(fields)!=REQUIRED_FIELDS:
            raise ValueError(f"Expected {REQUIRED_FIELDS} fields at line {lineno}: got {len(fields)}")
        title,en,assumptions,conclusion,formula,proof_hint,misuse,example,prereq_names=fields
        if any(not v.strip() for v in fields[:8]):
            raise ValueError(f"Missing core proof/counterexample/condition at line {lineno}")
        norm=_key(title)
        if norm in known:
            raise ValueError(f"Duplicate existing/seed concept name at line {lineno}: {title}")
        known.add(norm)
        level,domain,branch,topic,source=group
        cid="D123_"+hashlib.sha256((domain+"|"+title).encode("utf-8")).hexdigest()[:16]
        if cid in existing_ids:
            raise ValueError("Stable ID collision: "+cid)
        existing_ids.add(cid)
        source_title,url=REFERENCES[source]
        record={
            "id":cid,"cn":title,"en":en,
            "domain_cn":domain,"domain_en":DOMAINS[domain],
            "branch_cn":branch,"topic_cn":topic,"kind":"方法" if any(
                k in title for k in ("检验","策略","构造","算法","验证","反证","识别","估计","变换","计算","判据")) else "定理",
            "definition":assumptions+"；"+conclusion,
            "assumptions":assumptions,"conclusion":conclusion,
            "formulas":[formula],"level":level,"tags":["重要","专题深化","人工审核待完成"],
            "prereq":[],"prereq_status":"explicit_pedagogical_anchors_not_proof_dependencies",
            "example":example,"source_url":url,
            "source_locator":source_title+" / "+topic+"（主题参考，非逐条出处核实）",
            "reference_relation":"topic_reference_not_statement_certification",
            "verification_status":"authored_standard_fact_not_kernel_verified",
            "curation_status":"editorial_candidate_not_independently_reviewed",
            "level_status":"provisional_level123_subject_to_review",
            "importance_reason":"可复用的条件判断、推理链桥梁或高频反例；重要性是编辑候选，不是逐条核验结论",
            "statement_sha256":hashlib.sha256(("\n".join((assumptions,conclusion,formula))).encode()).hexdigest(),
            "proof_idea":proof_hint,"misuse_counterexample":misuse,
            "knowledge_origin":"authored_study_summary_of_existing_mathematics_not_new_discovery",
        }
        names[norm]=(cid,level,domain,prereq_names,lineno)
        authored.append(record)
        by_level[level]+=1
        by_domain[domain]+=1
    lookup={_key(r["cn"]):r["id"] for r in existing_rows}
    lookup.update({name:detail[0] for name,detail in names.items()})
    levels={r["id"]:r.get("level",5) for r in existing_rows}
    levels.update({detail[0]:detail[1] for detail in names.values()})
    for item in authored:
        raw=names[_key(item["cn"])][3]
        if not raw:
            continue
        parsed=[_key(t) for t in raw.split(";") if t.strip()]
        if len(parsed)!=len(set(parsed)):
            raise ValueError("Duplicate prereq for "+item["cn"])
        missing=[x for x in parsed if x not in lookup]
        if missing:
            raise ValueError(f"Unknown explicitly named prerequisite for {item['cn']}: {missing}")
        dependencies=[lookup[x] for x in parsed]
        if any(levels[x]>item["level"] for x in dependencies):
            raise ValueError("Prerequisite at higher level than dependent item: "+item["cn"])
        if item["id"] in dependencies:
            raise ValueError("Self prerequisite")
        item["prereq"]=dependencies
    return authored,{
        "deep_core_added":len(authored),"deep_core_by_level":dict(sorted(by_level.items())),
        "deep_core_by_domain":dict(sorted(by_domain.items())),
        "deep_core_seed_sha256":hashlib.sha256(seed.read_bytes()).hexdigest(),
        "deep_core_status":"editorial_candidates_not_independently_mathematically_reviewed",
    }
