# agent 管理操作封装为工具(ToolExport 动态发现注册)设计方案

## 目标

1. 把 agent 管理操作(list/get/create/update)包装成 LangChain 工具,供
   agent loop 的 LLM 调用(自管理:查看 agent、创建 agent、改名/改描述/
   启停 agent)。
2. **由 plugin 动态发现、注册**:工具不写死在组件里,而是新包
   `agent.tools` 以 `ToolExport` 声明式导出,经入口点被 `PluginDiscovery`
   发现;`/plugins install` 后由 `RuntimeMutationCoordinator._install_adapters`
   自动创建 tool-export 适配器,按作用域注册进 agent loop。
3. 每个工具带 **入参约束**(pydantic args_schema:agent_id 格式、
   `enabled=False` 时强制 `confirm="DISABLE"`)与 **提示词**(五要素
   description)。
4. **不暴露 delete_agent**——删除 agent 只能由 operator 经 API/CLI 执行。

## 现状

- `AgentRegistryProvider`(`langharness_core/plugins/agents/registry.py`,
  server 作用域)提供 `list_agents` / `get_agent` / `create_agent` /
  `update_agent` / `delete_agent`;`create_agent` 后 `agent-directory` 会为
  新 agent 物化 scope 与 loop(既有机制)。
- ToolExport 动态链路已具备:包贡献声明 `tool_exports`,install 时
  coordinator `_install_adapters` 查找 `plugin.tool_export.target` 规格
  服务并创建 `ToolExportAdapter`(`invoke_export(operation, arguments)`
  分发);适配器按 `target_scope` 落 `agent`(所有 loop)或注册作用域
  (`agent_instance`)。
- 包发现走 `langharness.plugins` 入口点(`dynamic-core` 已有先例)。
- `ToolExport.destructive` 字段已声明但无消费方;本方案只做标记。

## 词汇表

- 工具名:`list_agents` / `get_agent` / `create_agent` / `update_agent`
- confirm token:`DISABLE`(`update_agent` 的 `enabled=false` 时强制)
- agent_id 约束:`^[A-Za-z0-9._-]{1,64}$`(与 `validate_id` 一致)

## 设计

### 1. 导出服务 `agent-operations-export`

新文件 `src/langharness_core/plugins/agents/export.py`:

- `@ComponentFactory("agent-operations-export-factory")`
  `@Provides(ToolExportTarget)`(`plugin.tool_export.target` 规格),
  `plugin.name` = `agent-operations-export`。
- `@RequiresBest("_registry", AgentRegistryProvider, optional=True,
  immediate_rebind=True)` + `ContractGuard`;registry 未就绪时调用返回
  `{"error": "Agent registry unavailable"}`。
- `invoke_export(operation, arguments)` 分发:

| operation | 实现 |
| --- | --- |
| `list_agents` | `{"agents": registry.list_agents()}` |
| `get_agent` | `registry.get_agent(agent_id)`,不存在返回 `{"error": "Agent not found: ..."}` |
| `create_agent` | `registry.create_agent(agent_id, name, description)`(name/description 缺省空串,registry 内部回退) |
| `update_agent` | 只透传非 None 的 name/description/enabled 给 `registry.update_agent` |
| 其他 | `{"error": "Unknown operation: ..."}` |

- 统一捕获 `ValueError`(非法 id、不存在)→ `{"error": str(exc)}`,
  与既有管理工具的错误映射风格一致。

### 2. 包声明 `agent.tools`

`src/langharness_core/plugin.py` 新增 `agent_tools_package()`:

```python
PluginPackage(
    id="agent.tools",
    version="1.0.0",
    contributions=(
        PluginContribution(
            "agent-operations",
            "agent",
            PluginDescriptor(
                name="agent-operations-export",
                version="1.0.0",
                module="langharness_core.plugins.agents.export",
                factory="agent-operations-export-factory",
                instance="agent-operations-export",
                specification=SPEC_TOOL_EXPORT_TARGET,
                scope="agent",
                scope_parent="root",
                enabled=True,
            ),
            tool_exports=(
                ToolExport("list_agents", _list_agents_description, "list_agents", ListAgentsArgs),
                ToolExport("get_agent", _get_agent_description, "get_agent", GetAgentArgs),
                ToolExport("create_agent", _create_agent_description, "create_agent", CreateAgentArgs),
                ToolExport("update_agent", _update_agent_description, "update_agent", UpdateAgentArgs, destructive=True),
            ),
        ),
    ),
)
```

提示词(五要素,定义在 export.py,每个工具一组):

| 工具 | 要点 |
| --- | --- |
| `list_agents` | 列出全部 agent 及 enabled 状态;管理其他 agent 前先查。 |
| `get_agent` | 按 agent_id 查单个 agent;id 须匹配 `^[A-Za-z0-9._-]{1,64}$`。 |
| `create_agent` | 创建即上线(directory 自动物化 loop);先 list 避免重复 id;缺省 name 用 id。 |
| `update_agent` | 改名/改描述/启停;**enabled=false 必须传 `confirm='DISABLE'`**,停用后该 agent 的 loop 被拆除。 |

`update_agent` 完整示例:

> Update an agent's name, description, or enabled state. Only pass the
> fields you want to change. Disabling removes the agent's loop until
> re-enabled; it is semi-destructive, so enabled=false requires
> confirm='DISABLE' exactly. Example:
> update_agent(agent_id='billing', description='Handles invoices',
> enabled=False, confirm='DISABLE'). Returns the updated agent dict, or
> {"error": ...}.

schemas(定义在 export.py,与分发同文件):

- `ListAgentsArgs`:`BaseModel` 空 schema
- `GetAgentArgs` / `CreateAgentArgs`:`agent_id` 带 pattern 约束
- `CreateAgentArgs` 另含可选 `name` / `description`
- `UpdateAgentArgs`:`agent_id` + 可选 `name` / `description` / `enabled`
  + 可选 `confirm: Literal["DISABLE"]`;`model_validator` 强制
  `enabled is False → confirm == "DISABLE"`,否则校验失败

`pyproject.toml` 的 `[project.entry-points."langharness.plugins"]` 增加:

```toml
agent-tools = "langharness_core.plugin:agent_tools_package"
```

### 3. 动态发现与注册链路(框架既有)

```
/plugins install agent.tools agent-operations --scope agent
```

- discovery 经入口点扫到 `agent.tools`;install 时贡献 target 为
  `agent`,注册落 `agent` 作用域,导出服务随安装实例化(enabled=True)。
- `_install_adapters` 查 `plugin.tool_export.target@agent` → 为 4 个
  ToolExport 创建适配器实例,`target_scope="agent"` → 适配器落 `agent`
  作用域,**所有 agent loop 可见**,loop 重建后工具即入流程。
- enable/disable/restore 复用协调器既有机制;`dynamic.core` 同 module
  守卫不涉及本包。

### 4. 错误处理与提示词

- 错误统一 `{"error": ...}` 形状,LLM 可读后纠正(agent_id 非法、
  agent 不存在、registry 不可用)。
- 每个 ToolExport 的 description 五要素:一句话用途 / 何时用(创建后
  新 agent 自动上线;停用前确认影响)/ 约束(agent_id 格式、
  `enabled=false` 必须 `confirm='DISABLE'`)/ 简短示例 / 返回格式。

## 测试

沿用项目 TDD + `make check` 门槛(覆盖率 ≥95%):

- 单元:invoke_export 4 操作分发与错误映射(fake registry)、包声明
  (4 个 export 的 name/schema/target_scope、`destructive` 标记)、schema
  校验(agent_id 格式、`enabled=False` 缺 confirm 拒绝)、packaging 入口点。
- e2e(真 Pelix,沿用 `tests/test_dynamic_plugin_e2e.py` 模式):
  discover → install → agent 作用域工具集含 4 个名字;registry 服务
  (tmp agents.json)在场时经 `create_agent` 工具调用后 registry 出现新
  agent;disable 后工具消失。

## 涉及文件

- 新:`src/langharness_core/plugins/agents/export.py`(导出服务 + 4 schemas)
- 改:`src/langharness_core/plugin.py`(`agent_tools_package`)
- 改:`pyproject.toml`(entry point `agent-tools`)
- 新/改:单元与 e2e 测试(`test_agent_tools.py` 新、
  `test_dynamic_plugin_e2e.py` 追加、`test_packaging.py` 更新)
- 改:`README.md`(agent-tools 用法)
- 新:`docs/designs`/`docs/plans` 本文档与实现计划

## 边界与后续项

- v1 不暴露 `delete_agent`;单 agent(`agent:<id>`)可见性不做——同
  registration 的导出会同时在 `agent` 作用域生成适配器,单 agent 场景
  会工具重复,记为后续项。
- `ToolExport.destructive` 本方案仅标记(`update_agent` 为 True),消费方
  (拦截/过滤层)留给后续设计。
