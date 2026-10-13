"""数学知识树: 概念节点定义、JSON 加载、分层浏览与前置依赖图.

知识以"领域 -> 分支 -> 主题 -> 概念"四层组织, 数据存放在
``math_mcts/data/knowledge.json`` 中, 纯 Python 标准库即可读取.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DATA_PATH = Path(__file__).with_name("data") / "knowledge.json"
COLLISIONS_PATH = Path(__file__).with_name("data") / "collisions.json"


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

    def path(self) -> str:
        return f"{self.domain_cn} / {self.branch_cn} / {self.topic_cn}"

    def card(self) -> str:
        """概念卡片: 完整的可读信息块."""
        lines = [f"【{self.cn}】({self.en})  [{self.id}·{self.kind}]",
                 f"位置: {self.path()}",
                 f"难度: {'★' * self.level}{'☆' * (5 - self.level)} "
                 f"({self.level}/5)",
                 f"定义: {self.definition}"]
        if self.formulas:
            lines.append("公式: " + " ; ".join(self.formulas))
        if self.example:
            lines.append(f"例子: {self.example}")
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
        low = key.lower()
        for c in self.concepts:
            if c.cn == key or c.en.lower() == low:
                return c
        # 模糊: 名称包含
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
