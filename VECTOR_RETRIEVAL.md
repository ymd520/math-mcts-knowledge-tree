# 可选的全库 BM25 词项贡献缓存

当前入口保留纯标准库 SQL 后端；安装 `requirements-acceleration.txt` 后，
IndexedCorpus 自动尝试 NumPy 后端，并在 retrieval_profile 中报告实际后端。
不会自动安装依赖。固定索引校验、领域筛选、来源与审核状态不变。

## 算法与适用前提

SQLite 默认 BM25 按查询短语贡献求和；本实现从同一读取快照用 SQLite
逐短语取得原始贡献，以原查询顺序作 float64 累加。稀疏贡献存索引/分数数组，
密集贡献存完整分数数组；全部词项覆盖整个主索引，不改为精选或领域子库。
来源：https://www.sqlite.org/fts5.html#the_bm25_function 。

数组仅用来生成候选。截点附近保留 `1e-10*(1+最大分数绝对值)` 的保守
浮点余量，候选再交给原始完整 SQLite 查询评分，并按原 rowid 规则处理并列。
候选超过4096（包括过宽的并列组）时，回退原始全库排序，不截断并列组。
不得将这一浮点实现推广为任意自定义rank函数的通用精确算法。

## 边界与内存

- 词项缓存上限64 MiB、512项；工作数组受rowid范围预算约束。
- 无 NumPy、rowid范围过大、内存分配失败时，用原SQL并报告原因。
- 显式领域筛选继续用原带筛选SQL，不在此路径中近似处理领域。
- 数据库连接始终持有同一读取快照；缓存不跨索引版本或 corpus 实例复用。
- 不改变查询词、全库随机探索、MCTS奖励或实际知识ID记录。
- 大量独特词项、宽并列或缓存频繁淘汰时，未必更快；以实测为准。

## 性能报告

retrieval_profile 记录 term_score_loading、vector_accumulation、
vector_candidate_selection、candidate_match_and_rank、full_match_and_rank，
以及词项缓存命中/淘汰、回退次数、实际缓存字节与 NumPy 版本。
lexical_record_load_seconds 和 lexical_decode_seconds 保留卡片读取/解码计时。
这些子阶段不包括随机探索、报告解码和所有查询缓存get，不冒充全部I/O。
基准还记录 Linux 进程峰值RSS，用于比较速度和内存的交换。

## 被否决的路线

最初的“常见词组前k＋完整低频命中并集”路线，24次G5C实测虽保持全部
轨迹一致，却慢约4%～8%；96查询阈值筛选也没有收益。
它不再用于运行时，仅归档于 benchmarks/experiments/sparse_retrieval_rejected.py，
用于重现负面结果。不能把它描述为已成功加速。

## 验证

标准库回退与可选NumPy路径分别测试；随机短语、中文、词频差异、并列、
无命中、缓存预算、异常rowid与分配失败进行原SQL对照。
完整G5C配对基准比较每一次检索轨迹哈希及最终路径，不只检查最终路径。
这验证检索行为，不验证G5C数学结论。
