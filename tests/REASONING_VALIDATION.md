# v1.8.0 验证记录

基础版本：`fac438102d048105de88d395bcdc5ce50b3435a9`。
运行环境：Python 标准库；2026-10-13。

- `python tests/test_reasoning.py`：19 项测试通过。
  包含极值示例全部 32 种前提子集、3 个随机种子、30 个随机有限 Horn
  规则系统与独立闭包计算对照、20 层合成链和实际精选知识库适配。
- `python tests/test_mcts.py`：原有全部测试通过。
- `python -m compileall -q math_mcts tests/test_reasoning.py`：通过。
- `python -m math_mcts derive examples/extreme_value.json --iterations 80 -o examples/extreme_value_report.json`：
  输出相对于规则库的成功推导，4 次规则应用，实际依赖深度 3。
- `python -m math_mcts verify-derivation examples/extreme_value.json examples/extreme_value_report.json`：
  `valid_relative_to_rules: true`。

未运行 Lean 内核；未将原始导入语料自动转换为规则；未进行新成果查新。
20 层链与随机规则用于软件正确性检查，不是数学原创性证据。
