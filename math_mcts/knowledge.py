"""数学知识树: 概念节点定义、JSON 加载、分层浏览与前置依赖图.

知识以"领域 -> 分支 -> 主题 -> 概念"四层组织, 数据存放在
``math_mcts/data/knowledge.json`` 中, 纯 Python 标准库即可读取.
"""
from __future__ import annotations

import json
import gzip
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

DATA_PATH = Path(__file__).with_name("data") / "knowledge.json"
COLLISIONS_PATH = Path(__file__).with_name("data") / "collisions.json"
IMPORTED_DIR = Path(__file__).with_name("data") / "imported"
MODULE_INDEX_PATH = IMPORTED_DIR / "module_index.json"

# 导入语料的领域标签是 mathlib 顶层目录英文名, 与精选库 7 域中文体系不一致;
# 在 load_imported 装配 Concept 时统一映射, 保证碰撞"跨领域"判定语义正确.
# (分片原文不动, 审计链完整; 映射只发生在加载层.)
_IMPORT_DOMAIN_MAP = {
    "Algebra": ("代数", "Algebra"),
    "LinearAlgebra": ("代数", "Algebra"),
    "RingTheory": ("代数", "Algebra"),
    "GroupTheory": ("代数", "Algebra"),
    "NumberTheory": ("代数", "Algebra"),
    "FieldTheory": ("代数", "Algebra"),
    "RepresentationTheory": ("代数", "Algebra"),
    "AlgebraicGeometry": ("代数", "Algebra"),
    "Condensed": ("代数", "Algebra"),
    "Analysis": ("分析", "Analysis"),
    "MeasureTheory": ("分析", "Analysis"),
    "Dynamics": ("分析", "Analysis"),
    "Topology": ("几何与拓扑", "Geometry & Topology"),
    "Geometry": ("几何与拓扑", "Geometry & Topology"),
    "AlgebraicTopology": ("几何与拓扑", "Geometry & Topology"),
    "Probability": ("概率与统计", "Probability & Statistics"),
    "InformationTheory": ("概率与统计", "Probability & Statistics"),
    "Combinatorics": ("离散数学", "Discrete Math"),
    "Data": ("计算与优化", "Computing & Optimization"),
    "Computability": ("计算与优化", "Computing & Optimization"),
    "CategoryTheory": ("数学基础", "Foundations"),
    "Order": ("数学基础", "Foundations"),
    "SetTheory": ("数学基础", "Foundations"),
    "Logic": ("数学基础", "Foundations"),
    "ModelTheory": ("数学基础", "Foundations"),
    "Basic": ("数学基础", "Foundations"),
    "Other": ("数学基础", "Foundations"),
}


def _normalize_imported_domain(row: dict) -> tuple[str, str]:
    """把导入行的英文领域映射到精选库 7 域; 未知保留原文(不误分类)."""
    key = row.get("domain_en") or row.get("domain_cn") or ""
    return _IMPORT_DOMAIN_MAP.get(key, (row.get("domain_cn", key),
                                       row.get("domain_en", key)))


# 进程内缓存: 模块索引(前缀->分片文件列表), 避免重复读盘.
_SHARD_INDEX: dict | None = None


def _shard_index() -> dict:
    """读模块->分片索引(带进程内缓存). 索引为一次性构建的 sidecar 文件."""
    global _SHARD_INDEX
    if _SHARD_INDEX is None:
        _SHARD_INDEX = json.loads(MODULE_INDEX_PATH.read_text(encoding="utf-8"))
    return _SHARD_INDEX


@dataclass
class Concept:
    """单个数学概念节点."""

    id: str                      # 全局唯一编号, 如 "AN03"
    domain_cn: str               # 所属领域(中文), 如 "分析"
    domain_en: str               # 所属领域(英文), 如 "Analysis"
    branch_cn: str               # 所属分支, 如 "微积分"
    topic_cn: str                # 所属主题, 如 "极限与连续"
    cn: str                      # 概念中文名
    en: str                      # 概念英文名
    definition: str              # 一句话定义(零基础可读)
    formulas: list = field(default_factory=list)   # 关键公式(纯 Unicode)
    level: int = 1               # 难度 1(入门)-5(博士)
    prereq: list = field(default_factory=list)     # 前置概念 id 列表
    tags: list = field(default_factory=list)       # 如 ["核心"]
    kind: str = "概念"            # 知识类型: 概念/定理/推论/思路/公式/算法/分布…
    example: str = ""            # 一句话经典例子或适用场景(思路类必填)
    formal: str = ""             # 形式化陈述原文(如 Lean 定理语句)
    module: str = ""             # 来源模块(如 Mathlib.LinearAlgebra.Matrix)
    doc_url: str = ""            # 文档链接

    assumptions: str = ""
    conclusion: str = ""
    verification_status: str = ""
    curation_status: str = ""
    source_url: str = ""
    statement_sha256: str = ""
    statement_symbol_references: list = field(default_factory=list)
    reference_relation: str = ""
    original_metadata: dict = field(default_factory=dict)
    import_source_file: str = ""
    import_card_number: str = ""
    level_status: str = ""
    prereq_status: str = ""

    def path(self) -> str:
        return f"{self.domain_cn} / {self.branch_cn} / {self.topic_cn}"

    def card(self) -> str:
        """概念卡片: 完整的可读信息块."""
        lines = [f"【{self.cn}】({self.en})  [{self.id}·{self.kind}]",
                 f"位置: {self.path()}",
                 f"难度: {'★' * self.level}{'☆' * (5 - self.level)} "
                 f"({self.level}/5)",
                 f"定义: {self.definition}"]
        if self.formal:
            lines.append("形式陈述: " + self.formal)
        if self.verification_status:
            lines.append("核验状态: " + self.verification_status)
        if self.curation_status:
            lines.append("收录审核: " + self.curation_status)
        if self.source_url:
            lines.append("源码: " + self.source_url)
        if self.formulas:
            lines.append("公式: " + " ; ".join(self.formulas))
        if self.example:
            lines.append(f"例子: {self.example}")
        if self.module:
            lines.append(f"模块: {self.module}")
        if self.doc_url:
            lines.append(f"文档: {self.doc_url}")
        pre = "、".join(self.prereq) if self.prereq else "无"
        lines.append(f"前置: {pre}")
        if self.tags:
            lines.append("标签: " + "、".join(self.tags))
        return "\n".join(lines)

    def text_blob(self) -> str:
        parts = [self.cn, self.en, self.definition, self.branch_cn,
                 self.topic_cn, self.kind,
                 self.example] + list(self.tags) + list(self.formulas)
        return " ".join(parts)


class KnowledgeTree:
    """整棵数学知识树: 查询、层级浏览、前置依赖闭包."""

    def __init__(self, concepts: list[Concept], meta: dict | None = None,
                 collisions: list[dict] | None = None):
        self.meta = meta or {}
        self.concepts: list[Concept] = concepts
        self.by_id: dict[str, Concept] = {c.id: c for c in concepts}
        self.collisions: list[dict] = collisions or []
        # 碰撞速查: frozenset({a,b}) -> note
        self._collision_note: dict[frozenset, str] = {}
        for col in self.collisions:
            self._collision_note[frozenset((col["a"], col["b"]))] = \
                col["note"]
        self._build_hierarchy()
        # 名称索引: 精确查找 O(1). 23 万规模下线性扫描不可接受.
        self._name_index: dict[str, Concept] = {}
        for c in concepts:
            self._name_index.setdefault(c.cn, c)
            self._name_index.setdefault(c.en.lower(), c)

    # -- 加载 ------------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path = DATA_PATH,
             collisions_path: str | Path = COLLISIONS_PATH
             ) -> "KnowledgeTree":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        concepts = [Concept(**item) for item in raw["concepts"]]
        collisions: list[dict] = []
        if Path(collisions_path).exists():
            collisions = json.loads(
                Path(collisions_path).read_text(encoding="utf-8")
            )["collisions"]
        return cls(concepts, raw.get("meta", {}), collisions)

    @classmethod
    def load_imported(cls, *, module_prefix: str | list[str],
                      include_curated: bool = True) -> "KnowledgeTree":
        """Load an explicit module scope for searching/colliding imported statements.

        Imports retain pending curation status; symbol references are not prerequisites.
        A nonempty module prefix (or list of prefixes) is required to bound search
        and pair enumeration. 传多个前缀可做跨领域碰撞.

        规模优化: 用 module_index.json 只读包含该模块的分片(通常 1-2 个),
        而不是全量解压 20 个分片(234,576 条).
        """
        prefixes = [module_prefix] if isinstance(module_prefix, str) else list(module_prefix)
        if not prefixes or any(not p.startswith("Mathlib.") for p in prefixes):
            raise ValueError("Specify a nonempty Mathlib module prefix")
        root = IMPORTED_DIR
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        shard_by_name = {item["shard"]: item for item in manifest["files"]}
        wanted: set[str] = set()
        for p in prefixes:
            hit = _shard_index().get(p)
            if hit:
                wanted.update(hit)
            else:
                # 索引未命中: 回退到按模块名前缀匹配分片(慢路径, 保证正确性)
                wanted.update(item["shard"] for item in manifest["files"])
        base = cls.load() if include_curated else cls([])
        concepts = list(base.concepts)
        existing = {(c.module, c.en, c.formal) for c in concepts if c.formal}

        def in_scope(module: str) -> bool:
            return any(module == p or module.startswith(p + ".") for p in prefixes)

        for shard in sorted(wanted):
            item = shard_by_name[shard]
            path = root / shard
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != item["shard_sha256"]:
                raise ValueError(f"Import shard hash mismatch: {path.name}")
            for row in json.loads(gzip.decompress(data))["concepts"]:
                module = row["module"]
                if not in_scope(module):
                    continue
                key = (module, row["en"], row["formal"])
                if key not in existing:
                    # 规格一致: 领域标签映射到精选库 7 域中文体系
                    dcn, den = _normalize_imported_domain(row)
                    row = {**row, "domain_cn": dcn, "domain_en": den}
                    concepts.append(Concept(**row))
                    existing.add(key)
        scope = prefixes[0] if len(prefixes) == 1 else prefixes
        return cls(concepts, {**base.meta, "import_scope": scope}, base.collisions)

    def collision_note(self, a: str, b: str) -> str | None:
        """返回概念对 (a,b) 的 curated 碰撞说明, 无则返回 None."""
        return self._collision_note.get(frozenset((a, b)))

    # -- 基本查询 --------------------------------------------------------
    def get(self, cid: str) -> Concept:
        return self.by_id[cid]

    def find(self, name: str) -> Concept:
        """按中文名 / 英文名 / id 查找概念, 找不到抛 KeyError."""
        key = name.strip()
        if key in self.by_id:
            return self.by_id[key]
        hit = self._name_index.get(key) or self._name_index.get(key.lower())
        if hit is not None:
            return hit
        # 模糊: 名称包含
        low = key.lower()
        for c in self.concepts:
            if key in c.cn or low in c.en.lower():
                return c
        raise KeyError(f"未找到概念: {name!r}")

    def domains(self) -> list[tuple[str, str]]:
        seen: dict[str, str] = {}
        for c in self.concepts:
            seen.setdefault(c.domain_cn, c.domain_en)
        return list(seen.items())

    # -- 层级浏览(供 MCTS 概念检索使用) ----------------------------------
    def _build_hierarchy(self) -> None:
        # key: () -> domain -> branch -> topic -> concept id
        self._kids: dict[tuple, list[tuple]] = {}
        self._label: dict[tuple, str] = {(): "数学"}
        for c in self.concepts:
            d = ("d", c.domain_cn)
            b = ("d", c.domain_cn, "b", c.branch_cn)
            t = ("d", c.domain_cn, "b", c.branch_cn, "t", c.topic_cn)
            leaf = ("c", c.id)
            for parent, child, label in [
                ((), d, c.domain_cn), (d, b, c.branch_cn),
                (b, t, c.topic_cn), (t, leaf, c.cn),
            ]:
                self._kids.setdefault(parent, [])
                if child not in self._kids[parent]:
                    self._kids[parent].append(child)
                self._label.setdefault(child, label)

    def hierarchy_children(self, node: tuple) -> list[tuple]:
        return list(self._kids.get(node, []))

    def hierarchy_label(self, node: tuple) -> str:
        return self._label.get(node, "?")

    def is_concept_leaf(self, node: tuple) -> bool:
        return len(node) == 2 and node[0] == "c"

    def leaf_concept(self, node: tuple) -> Concept:
        return self.by_id[node[1]]

    # -- 前置依赖 --------------------------------------------------------
    def prereq_closure(self, cid: str) -> list[str]:
        """返回掌握 cid 之前必须先掌握的全部前置 id (拓扑有序)."""
        order: list[str] = []
        seen: set[str] = set()

        def visit(x: str) -> None:
            if x in seen:
                return
            seen.add(x)
            for p in self.by_id[x].prereq:
                visit(p)
            order.append(x)

        visit(cid)
        return order[:-1]  # 去掉自身

    def check_integrity(self) -> list[str]:
        """完整性自检: 返回问题描述列表, 为空表示通过."""
        problems: list[str] = []
        if len(self.by_id) != len(self.concepts):
            problems.append("Duplicate concept IDs")
        for c in self.concepts:
            if not 1 <= c.level <= 5:
                problems.append(f"{c.id}: level 非法 ({c.level})")
            for p in c.prereq:
                if p not in self.by_id:
                    problems.append(f"{c.id}: 前置 {p} 不存在")
                elif p == c.id:
                    problems.append(f"{c.id}: 前置指向自身")
        # 环检测
        color: dict[str, int] = {}

        def dfs(x: str, stack: list[str]) -> None:
            color[x] = 1
            stack.append(x)
            for p in self.by_id[x].prereq:
                if p not in self.by_id:
                    continue
                if color.get(p) == 1:
                    problems.append("环: " + " -> ".join(stack + [p]))
                elif color.get(p) != 2:
                    dfs(p, stack)
            stack.pop()
            color[x] = 2

        for c in self.concepts:
            if color.get(c.id) != 2:
                dfs(c.id, [])
        return problems
