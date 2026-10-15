# Math-MCTS：ChatGPT ↔ 数学知识库扩展接口（AI Candidate Bridge）

## 作用和信任边界

用户可要求 ChatGPT 将熟悉的**定理、定义、解题方法、反例候选、
启发式和待检验猜想**写成固定 JSON knowledge pack，保存为仓库文件，
然后通过统一入口批量导入本地独立 SQLite 候选仓库，供 MCTS
检索、提议跨领域组合、创建进一步研究任务。

这是**一个可审计的知识交换协议**，不是模型权重或内部训练资料
的直接导出；模型生成的内容可能有错。

本接口与既有 `source_expansion`（固定版本外部文献）和
`RuleBook`（调用方明确审核的合法推理规则）是**不同信任层**：

| 分类 | 储存/运算 | 信任状态 |
|---|---|---|
| curated 数学知识 | 原有 manifest 和受控目录 | 不受本接口影响 |
| 外部固定文献引文 | `source_expansion` | 待审核外部候选 |
| **AI 生成内容** | `math_mcts.ai_knowledge` 独立 SQLite | **永远默认未审核** |
| 可执行推理规则 | 显式审核的 typed `RuleBook` | 不接受 AI 候选自动升级 |
| MCTS 碰撞/启发式 | `collide_concepts` | 只是搜索提示，不是数学证明 |

用户提供的 model/provider 信息也是**自报记录**，导入器不验证它确实来自
某个 ChatGPT 会话。参考书、论文网址如有填写，保留为
`not_verified_by_importer` 的待核查引用；没有真实文献时用空数组，
禁止编造作者、页码或论文链接。

## 一、一次性运行

```bash
# 1. 导入我整理的18条已知数学事实/证明方法的未审核知识包
python tools/ai_knowledge_cli.py ingest examples/ai_knowledge_seed_v1.json --db ai.sqlite

# 2. 读取待核验候选（普通 SQLite 全文检索 + 原有精确排序）
python tools/ai_knowledge_cli.py search "Lagrange" --db ai.sqlite --limit 10

# 3. 把 AI 候选放入临时 KnowledgeTree，真正运行现有 MCTS 两两碰撞
python tools/ai_knowledge_cli.py collide --db ai.sqlite --limit 30 --iterations 1000

# 4. 检查引用与知识数量，确保没有悄悄升级为 reviewed
python tools/ai_knowledge_cli.py inventory --db ai.sqlite
```

`ai.sqlite` 是**本地持久化数据库**，独立于正式数学知识仓库；
它不会自动提交到 GitHub。若要跨设备同步，建议只版本化
有审核记录的 JSON knowledge packs，在目标电脑重新导入即可。

## 二、给 ChatGPT 的写入协议

可以让 ChatGPT 依照 `examples/ai_knowledge_seed_v1.json` 生成更多
JSON pack，将其保存到 `knowledge_packs/...` 或自己的工作目录。

顶层必须包含：

```json
{
  "schema": "math-mcts-ai-knowledge-v1",
  "generator": {
    "system": "ChatGPT",
    "model": "GPT-6",
    "run_id": "research-20261015-session01",
    "generated_at": "2026-10-15"
  },
  "items": [
    {
      "local_id": "UNIQUE-001",
      "kind": "theorem",
      "domain": "代数",
      "branch": "线性代数",
      "topic": "线性映射",
      "title": "秩-零化度定理",
      "statement": "For linear T:V→W and finite-dimensional V, dim(V)=rank(T)+nullity(T).",
      "assumptions": "V finite-dimensional over a field; T linear.",
      "conclusion": "dim(V)=dim(im T)+dim(ker T)",
      "explanation": "已知数学定理的检索卡片，不声称原创。",
      "proof_idea": "Extend a basis of ker T.",
      "falsification_plan": "Check edge cases V={0} and zero map.",
      "keywords": ["linear algebra", "rank", "nullity"],
      "references": []
    }
  ]
}
```

`kind`：`definition/theorem/lemma/method/conjecture/counterexample/
heuristic/reduction/proof_idea`。条件和结论都必须明确，不允许只写标题。
同一批次 `local_id` 唯一；同一个 `generator.run_id/local_id`
后续改变内容会使整个事务回滚，修订要新建新的 run_id。

**不能传入 `verified=true`、`core`、`importance_status`、
`curation_status`、`level=1` 等字段来绕过审核。**
任何未知字段直接拒绝而不是相信模型自评。

## 三、去重、检索与 MCTS 接口

`ingest_pack(db,pack)`：
- 类型、字段、字符长度、数组规模、引用 URL 约束；
- 单批原子事务；非法条目、重复局部 ID 或相同 run/local ID
  内容冲突导致全批拒绝；
- 按 `kind,domain,statement,assumptions,conclusion` 的 NFKC
  空白归一化产生确定性候选 ID；
- 相同文本不同生成批次增加独立来源观察记录；
- 名称、证明提示、反例检验建议和未审核来源信息保存至候选库；
- **字符串重复不代表两个定理在数学上等价**。

`lookup(db,query)`：SQLite FTS5 索引的**候选检索**。

`candidate_tree(db, query=..., limit=..., base_tree=...)`：
从数据库选出受限数量的候选，转换成原有的
`KnowledgeTree` 中 `Concept` 的**只读临时视图**。
标签固定为 `AI候选、未核验`，其 Level=5 仅为旧接口要求的
**未评级占位符**（`level_status=ungraded_ai_candidate`）。
不给任何候选添加 `核心`、`重要`、`reviewed` 或有效先修边。

`query_for_research(db,query)` 使用现有
`search_concepts` 的**精确重排序**，**不是 MCTS**。如需真正的
MCTS 计算，用 `collide_for_research(db, iterations=...)`，内部调用
`collide_concepts`，探索不同领域候选的配对；
报告 `conjecture_only=true`、`proof_verified=false`。

**注意：MCTS 知识碰撞提供的是潜在有趣的关系，不代表归纳出了
新定理，更不能把匹配卡片自动变成推理规则。** 研究中可由 GPT
读取这个列表，提出有明确适用条件的辅助猜想，再交由独立
Verification 流程证明或证伪。

## 四、下一阶段扩展点

- 多次 ChatGPT 提议 → knowledge packs → AI 候选 DB →
  有界 MCTS 组合 → ChatGPT 研究分析 → 明确反例/证明任务；
- 用户或独立验证模块审核材料后，**走既有受审规则引入流程**，
  不能通过本桥偷偷修改 RuleBook；
- 长期可把这个 JSON contract 扩展成经用户授权的可写插件/工作流，
  但本实现不包含后台持续运行、自动从模型读取参数或直接网络服务。

```bash
python tests/test_ai_knowledge_bridge.py
```

不修改 `curated/manifest.json` 中的正式版本号；
不更改正式重要数学知识等级和已证结论数。
