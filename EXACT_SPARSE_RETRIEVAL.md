# 已否决的常见词组/低频并集路线

此方案已完成24次G5C配对测试：检索轨迹一致，但耗时增加约4%～8%。
96条固定查询的128、512、2048、8192四组阈值筛选均没有改善。
它不作为运行时默认后端。原始实现归档在
[benchmarks/experiments/sparse_retrieval_rejected.py](benchmarks/experiments/sparse_retrieval_rejected.py)。
后续路线与实际后端说明见 [VECTOR_RETRIEVAL.md](VECTOR_RETRIEVAL.md)。
