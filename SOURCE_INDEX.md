# 数学源码知识图与 MCTS 索引

新增加 `source_index/`：固定版本 mathlib4 源码索引、离线可复现构建、来源和许可证、真实 UCT 知识检索。它与原有经过编辑的概念卡分层使用。

```sh
python source_index/src/bootstrap.py
python source_index/src/mcts.py --query "finite group convolution" --iterations 2000 --depth 30
```

完整说明：[source_index/README.md](source_index/README.md)。

已完成本地验证的索引规模：8,619 个源模块，221,184 个声明位置；这些位置包含基础设施与辅助引理，不能当作同等数量的重要数学定理。归档与数据库通过固定来源、SHA-256 和构建脚本再现，不直接提交大文件。
