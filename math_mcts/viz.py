"""MCTS 搜索树可视化: 导出 Graphviz DOT 格式.

把某次 MCTS 运行的搜索树画出来, 节点标注访问次数与平均回报,
直观看到 UCB 把算力集中到了哪些分支.
用 `dot -Tpng tree.dot -o tree.png` 渲染(需安装 graphviz).
"""
from __future__ import annotations


def to_dot(root, label_fn=None, max_nodes: int = 300) -> str:
    """将 MCTS 搜索树导出为 DOT 字符串.

    label_fn: 状态 -> 显示文本, 默认 str(state).
    """
    label_fn = label_fn or (lambda s: str(s)[:28])
    lines = ["digraph MCTSTree {",
             '  node [shape=box, fontname="sans-serif"];',
             '  edge [fontname="sans-serif"];']
    count = [0]

    def esc(s: str) -> str:
        return s.replace('"', "'").replace("\n", "\\n")

    def visit(node, nid: int) -> None:
        if count[0] >= max_nodes:
            return
        text = (f"{esc(label_fn(node.state))}\\n"
                f"访问{node.visits}次 均值{node.mean:.2f}")
        lines.append(f'  n{nid} [label="{text}"];')
        # 按访问次数排序, 只展开最值得看的子节点
        kids = sorted(node.children,
                      key=lambda ch: ch.visits, reverse=True)
        for ch in kids:
            if count[0] >= max_nodes:
                break
            count[0] += 1
            cid = count[0]
            visit(ch, cid)
            act = esc(str(ch.action)[:20]) if ch.action is not None else ""
            lines.append(f'  n{nid} -> n{cid} [label="{act}"];')

    visit(root, 0)
    lines.append("}")
    return "\n".join(lines)
