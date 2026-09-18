# agent scope 默认 LLM(providers.default 映射)设计方案

## 目标

服务器启动(agent materialize)时,在 `agent` scope 下创建一个默认 LLMPlugin
实例,其属性由 `providers.default` 映射而来。每个 agent loop 通过 scope
继承该实例;agent 自己指定了 llm(存储配置或 `/stream` 动态创建)时,最近
scope 的实例遮蔽默认,移除后自动回落。

## 语义

- 默认实例 `llm@default` 挂在 scope `agent` 下,不带 `plugin.agent_id`:
  - 不匹配任何 loop 的 `_llm_provider` 过滤条件 `(plugin.agent_id=X)`;
  - 只通过 `_scoped_llm_providers` 的可见性过滤器(含 scope `agent`)进入
    loop,由 `resolve_scoped_best` 按最近 scope + plugin_key 选出。
- agent 自己的 llm(`llm@<agent_id>`,scope `agent:<id>`)距离为 0,遮蔽
  scope `agent` 的默认(距离 1);agent 实例被 kill 后 loop 回落到默认。
- `/stream` 行为不变:不传 model 且 agent 无存储 llm 配置时仍返回 400;
  传入的 payload 仍按现有逻辑生成 agent 自己的 llm 实例。
- `providers.default` 缺失或校验失败:记录 warning,不创建默认实例,
  行为与本次改动前一致(loop 无 llm 直到有实例产生)。

## 字段映射

`providers.default` → 默认实例属性:

| 配置字段 | 插件属性 |
|---|---|
| `model` | `plugin.model.name` |
| `api_key` | `plugin.model.api_key` |
| `base_url` | `plugin.model.base_url` |
| `protocol` | `plugin.model.protocol` |

## 实现

- `src/langharmess_core/plugin.py`:新增 `default_llm_descriptor(properties)`
  ——llm 模块实例 `llm@default`,scope `"agent"`、scope_parent `"root"`。
- `src/langharmess_core/plugins/agents/directory.py`:
  - `@RequiresBest("_configs_service", Configs, optional=True,
    immediate_rebind=True)` + ContractGuard(import 自
    `langharmess_config.contracts`,与 api 层同模式);字段名避开目录已有
    的存储绑定配置 `_configs`。
  - `_materialize_all()` 先幂等调用 `_ensure_default_llm()`:读取
    `get_default_provider()`,映射字段后 `instantiate_instance(descriptor,
    scope_id=AGENT_SCOPE_ID, plugin_key="llm")`;默认实例先于任何 loop
    创建,loop `@Validate` 时即可解析到。
  - `_on_scope_unbind` 时重置 `_default_llm = None`。
- 遮蔽/回落零新增代码:现有 `resolve_scoped_best` + 可见性过滤已覆盖,
  见 `tests/test_scope_plugin_e2e.py` 的 shadowing e2e。

## 测试

- `tests/test_agent_directory.py`:默认实例创建与字段映射;无 configs
  服务不创建;缺省时 warning 不创建;重复 materialize 幂等;configs 迟到
  绑定时补建;agent 自有 llm 与默认共存。
- `tests/test_default_llm_e2e.py`:真实 PluginManager + 真实
  ConfigsPlugin/TOML 配置端到端——loop 继承默认实例(`_plugin_scope_id
  == "agent"`)、`ensure_plugin_instance` 后遮蔽为自有模型、reload 后回
  落到默认。

## 非目标

- `/stream` 的 400 检查与按请求生成 agent llm 的既有行为不改。
- 不新增 provider 指针机制;`default` 仍为保留名。
- 配置文件运行时热更新默认实例不在本次范围。
