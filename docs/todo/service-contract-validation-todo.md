# 服务契约校验 · 任务清单与进度

**分支：** `feature/service-contract-validation`
**计划：** [docs/plans/2026-09-14-service-contract-validation-plan.md](../plans/2026-09-14-service-contract-validation-plan.md)
**设计：** [docs/designs/2026-09-14-service-contract-validation-design.md](../designs/2026-09-14-service-contract-validation-design.md)
**执行方式：** subagent 逐任务实现 + 两阶段审查（规格符合性 → 代码质量）；每任务一个提交，提交前 `make check` 全门禁（ruff → mypy strict → pyright → 干净进程导入 → pytest 覆盖率 ≥95%）。

**更新时间：** 2026-09-14

## 进度

| # | 任务 | 状态 | 提交 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | `service_contract` 装饰器与契约注册表 | ✅ 完成 | `a2c265a` | 两阶段审查通过 |
| 2 | 契约签名提取 `describe()` | ✅ 完成 | `bf6706b` | 两阶段审查通过 |
| 3 | 注解兼容判定（Any 通配 / union 归一 / 返回协变） | ✅ 完成 | `a38c28e`、`dfb51d1`、`4ad6efa` | 审查后修 2 处：Callable 参数列表 `Any` 通配失效；返回位置 union 方向反了 + 普通类协变不可达 |
| 4 | 方法存在性与参数形状校验 | ✅ 完成 | `14c699c` | `PARAM_EXTRA_REQUIRED` 改为位置感知（计划片段与自身测试矛盾）；已知窄边界见计划回填 |
| 5 | `ContractViolationError` 与消息格式 | ✅ 完成 | `5701622` | 两阶段审查通过 |
| 6 | `ContractGuard` 消费侧隔离 | ⏳ 审查中 | `5f3e129` | 实现与门禁完成（216 passed / 95.51%）；规格审查待跑 |
| 7 | `PluginManager` 安装侧硬拦 | ⬜ 待开始 | — | 违规组件 kill + 抛错，不进 `_bound` |
| 8 | 核心契约 pin 与 `AgentLoopProvider` | ⬜ 待开始 | — | core 15 个 Protocol 加 pin + 新增 `AgentLoopProvider` |
| 9 | 核心插件声明迁移（`@Provides`） | ⬜ 待开始 | — | 18 个核心模块 SPEC_X → Protocol 类 |
| 10 | agent loop 绑定守卫 | ⬜ 待开始 | — | 15 个字段接 `ContractGuard`；e2e 加"绕过安装期注册的坏服务被隔离"测试 |
| 11 | API/CLI/Config/Logging 契约 pin 与声明迁移 | ⬜ 待开始 | — | 含补 `APIServerProvider`、`register_service` 改用类规格 |
| 12 | API 侧守卫与 `/stream` 400 | ⬜ 待开始 | — | app 6 + stream 2 + configs 1 个字段；违规插件安装返回 400 |
| 13 | `examples/plugin_demo` 最小同步 | ⬜ 待开始 | — | 引用真实契约 + provider 补注解与 `get_protocol` |
| 14 | 规则固化与文档 | ⬜ 待开始 | — | `AGENTS.md` 增服务契约规则 |

## 过程记录

- 计划外提交（文档回填，均已单独提交）：`b1b712e`（Task 3 语义修正）、`7811771`（Task 4 取舍）、`ad685ce`（错误消息格式对齐）。
- Task 3 审查发现的两个语义问题会在 Task 7 硬拒绝生效前造成**安装期误拒**，已优先修复：
  - `Callable[[Any], X]` 里的 `Any` 不再失去通配；
  - 契约 `-> str | None` 接受实现 `-> str`（收窄），契约 `-> int | str` 拒绝实现 `-> int | str | None`（放宽）；
  - 返回位置普通类允许子类（`issubclass`），参数位置保持不变性。
- 已知限制（记录在代码与计划中）：`_parameter_problems` 用位置前缀启发式判定 extra-required，契约 `run(value)` vs 实现 `run(force, value)` 会漏报；彻底解决需改用 `inspect.Signature.bind` 模拟调用。
- 覆盖率余量偏薄（当前 95.51%，门禁 95%），后续任务的新增分支需自带测试。

## 验收清单（全部任务完成后）

- [ ] `make check` 全绿（覆盖率 ≥95%）。
- [ ] `tests/test_contract_enforcement.py` 覆盖安装期拒绝、绑定期隔离、未 pin 规格跳过。
- [ ] `tests/test_e2e.py` 三协议路径行为不变；新增"直接注册坏服务被隔离"用例。
- [ ] 字符串规格名回归：`get_service_reference("agent.plugin.llm")` 仍命中。
- [ ] 手动：`.venv/bin/python examples/plugin_demo/run_demo.py` 输出正常。
- [ ] 可选：按 AGENTS.md 真实端到端流程跑一轮 `/stream`。
