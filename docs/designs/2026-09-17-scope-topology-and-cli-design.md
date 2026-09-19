# Scope 固定拓扑、常量集中与 /scope 接口设计方案

## 目标

1. 运行时 scope 拓扑固定为：

   ```
   root → server
   root → agent
   root → ui
   agent → agent:{agent_id}
   ```

   （agent 实例 scope ID 统一为冒号格式 `agent:{agent_id}`，与 API 配置层
   的 `agent:<id>` 命名风格一致。）

2. 固定 SCOPE_ID 集中到 `src/langharness_plugin/scope_const.py`，作为唯一
   权威来源，消除当前多处重复定义。

3. CLI 提供 `/scope` 交互命令，显示 scope 树。

## 现状问题

- 规范常量散落：`ROOT_SCOPE_ID` 在 `langharness_scope/model.py`；
  `UI/SERVER/AGENT_SCOPE_ID` 与 `agent_instance_scope_id` 在
  `langharness_core/scopes.py`；而描述符里全是裸字符串
  `scope="server"` / `scope_parent="root"` 等。
- `PLUGIN_SCOPE_ID`、`PLUGIN_KEY` 在 `scope_policy.py` 与
  `plugin_manager.py` 各定义一份。
- `agent` 父级不一致：生产描述符 agent→server，测试里有的 agent→root。
- `ui` scope 在生产代码中从未被种入（仅测试使用），`UI_SCOPE_ID` 是死常量。

## 固定拓扑声明

`src/langharness_plugin/scope_const.py`（新文件）：

```python
from langharness_scope import ROOT_SCOPE_ID, ScopeId

UI_SCOPE_ID = ScopeId("ui")
SERVER_SCOPE_ID = ScopeId("server")
AGENT_SCOPE_ID = ScopeId("agent")

PLUGIN_SCOPE_ID = "plugin.scope_id"
PLUGIN_SCOPE_CHAIN = "plugin.scope_chain"
PLUGIN_KEY = "plugin.key"

# (scope_id, name, parent_id) —— 内置固定拓扑，父级均为 root
BUILTIN_SCOPES: tuple[tuple[ScopeId, str, ScopeId | None], ...] = (
    (UI_SCOPE_ID, "UI", ROOT_SCOPE_ID),
    (SERVER_SCOPE_ID, "Server", ROOT_SCOPE_ID),
    (AGENT_SCOPE_ID, "Agent", ROOT_SCOPE_ID),
)


def agent_instance_scope_id(agent_id: str) -> ScopeId:
    return ScopeId(f"agent:{agent_id}")
```

- `ScopeId` 类型与 `ROOT_SCOPE_ID` 的值仍定义在 `langharness_scope`
  （底层包不能反向依赖 plugin 层），在此再导出，保证 scope 相关代码
  只从 scope_const 一个入口导入。
- 元数据 key `PLUGIN_SCOPE_ID` / `PLUGIN_SCOPE_CHAIN` / `PLUGIN_KEY`
  一并迁入，`scope_policy.py` 与 `plugin_manager.py` 改为导入，删除
  各自的本地定义。
- `langharness_core/scopes.py` 删除，其消费方
  （`plugins/agents/directory.py`、`core/plugin.py`）改从 scope_const 导入。

## PluginManager 全局种子

- `PluginManager.start()` 末尾调用 `_seed_builtin_scopes()`：
  遍历 `BUILTIN_SCOPES`，scope 不存在则 `scope_tree.create`；已存在且父级
  不同则抛 `ValueError`（沿用 `ensure_scope` 的冲突语义）。
- 所有进程（ui / server 模式）启动即种入固定拓扑；UI 进程的树也含
  server/agent（已知无实际用途，接受）。
- 描述符调整：
  - `src/langharness_core/plugin.py` 中 agent 作用域模板描述符的
    `scope_parent` 由 `"server"` 改为 `"root"`（4 处）。
  - `coordinator.py` `_install_adapters` 中工具导出适配器的
    `scope_parent` 由 `"server"` 改为 `ROOT_SCOPE_ID`。
  - `coordinator.py` `_descriptor` 的 `scope_parent="agent"` 不变
    （agent:{id} 仍挂在 agent 下）。

## 冒号格式迁移与旧数据兼容

- `agent_instance_scope_id` 生成 `agent:{agent_id}`。
- `coordinator.py`：
  - `_descriptor` 的合法性检查 `startswith("agent/")` 改为
    `startswith("agent:")`，suffix 由 `/`→`-` 改为 `:`→`-`
    （实例名 `xxx@agent-a` 不变）。
  - `_install_adapters` 的 `target_scope.startswith("agent/")` 同步改为
    `startswith("agent:")`。
- 旧持久化数据迁移：`_restore_scopes` 改为"已存在则跳过"（不再
  `ensure_scope` 强校验父级）——种子先行保证内置 scope 是规范父级，旧的
  agent→server 数据自动让位；同时跳过旧格式遗留的 `agent/<id>` scope。
  下次 `_persist_once` 时快照自动重写为规范拓扑。

## API：GET /scope

- `DynamicPluginManager` 协议新增 `scopes() -> tuple[Scope, ...]`；
  coordinator 实现为 `self.manager.scope_tree.snapshot().scopes` 的委托。
- 新路由插件 `src/langharness_api/plugins/routes/scopes.py`
  （`api-scopes-route-factory`），仿 `routes/plugins.py` 模式：绑定
  `DynamicPluginManager`（optional + immediate_rebind + ContractGuard），
  未绑定时返回 503。
- 路由：`GET /scope` → `{"scopes": [{"id", "parent_id", "name"}, ...]}`。
- `langharness_api/plugin.py` 增加 `api-scopes` 描述符
  （spec=SPEC_ROUTE，scope="server"，scope_parent="root"）与贡献项。
- 鉴权：沿用 API 现有全局鉴权（CLI 已带 Bearer token，与 /health、
  /plugins 一致），不做特殊处理。

## CLI：/scope 交互命令

- 新命令插件 `src/langharness_cli/plugins/commands/scope.py`
  （`cli-scope-command-factory`），提供 `CLICommandProvider`：
  - `get_interactive_commands()` → `/scope`，GET `{base_url}/scope`，
    渲染缩进树（子节点排序，最后一个子节点用 `└──`，其余 `├──`）：

    ```
    root
    ├── ui
    ├── server
    └── agent
        └── agent:a
    ```

  - `get_commands()` → argparse 版 `scope` 子命令，输出原始 JSON
    （与 health/plugins 命令的双接口模式一致）。
- `langharness_cli/plugin.py` 注册 `cli-scope` 描述符
  （scope="ui"，scope_parent="root"）与贡献项。

## 测试

更新：
- `agent/a` → `agent:a`：test_runtime_mutation_coordinator、
  test_dynamic_plugin_e2e、test_scope_plugin_e2e、test_plugin_manager_scoped、
  test_agent_directory。
- 拓扑断言：test_dynamic_plugin_e2e / test_scope_plugin_e2e 中 agent 父级
  由 server 改为 root；test_scope_plugin_e2e 中"agent 默认父级 root"用例
  保持并成为规范行为。
- 注意 pelix 模块重载限制：涉及 bootstrap 的用例按模式拆分。

新增：
- test_scope_const：ID 值、`agent_instance_scope_id("a") == ScopeId("agent:a")`、
  BUILTIN_SCOPES 声明、再导出完整性。
- PluginManager 种子行为：start 后树含 root/ui/server/agent；重复种子幂等；
  父级冲突抛 ValueError。
- `GET /scope` 路由测试（含 503 场景）。
- CLI `/scope` 命令测试（树渲染输出）。

## 涉及文件

- 新增 `src/langharness_plugin/scope_const.py`
- 新增 `src/langharness_api/plugins/routes/scopes.py`
- 新增 `src/langharness_cli/plugins/commands/scope.py`
- 修改 `src/langharness_plugin/plugin_manager.py`（导入 + 种子）
- 修改 `src/langharness_plugin/scope_policy.py`（导入常量）
- 修改 `src/langharness_plugin/contracts.py`（scopes() 协议）
- 修改 `src/langharness_plugin/coordinator.py`（冒号格式、scope_parent、
  恢复语义）
- 删除 `src/langharness_core/scopes.py`；修改
  `src/langharness_core/plugin.py`、`src/langharness_core/plugins/agents/directory.py`
- 修改 `src/langharness_api/plugin.py`、`src/langharness_cli/plugin.py`
- 修改/新增对应测试文件
