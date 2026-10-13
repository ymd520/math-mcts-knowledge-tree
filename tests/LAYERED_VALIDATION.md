# v1.9.0 分层碰撞验证记录

基础提交：`b713285e7b1f35463e427cdcacfd604c42f844d2`。
2026-10-13，Python 标准库环境。

- `python tests/test_layered.py`：12 项分层测试通过。
- `python tests/test_reasoning.py`：19 项推导测试通过。
- `python tests/test_mcts.py`：原有全部测试通过。
- `python -m compileall -q math_mcts tests/test_layered.py examples/layered_collision.py`：通过。
- CLI 集成：生成20×20输入、derive-layers输出完整证书、verify-layers重放成功；
  修改证书中的规则ID后验证失败，进程返回码为1。
- 三个种子1/7/19独立运行20×20合成图，各5次MCTS迭代，均得到深度20、
  400次规则应用、逐层目标相关前提数量20。计时见
  `examples/layered_validation.json`，不用于宣称一般性能优势。
- 21×21输入得到实际深度21、441次规则应用。
- 每层20前提/1结论的20层链成功；删除必要前提、重复前提、无关分支凑宽度、
  同层借用新结论、浅层目标、证书篡改及候选预算截断得到预期结果。

测试使用人工指定的正Horn蕴含关系，不构成原创数学证据。文本自动翻译、Lean
内核、通用猜想发现和反例后端未接入。
