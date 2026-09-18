# Plugin 操作强制 scope、list/config 聚合所有 scope 设计方案

## 目标

1. 所有 plugin 变更操作必须指定 scope；未指定时明确提示用户，非交互模式
   报错退出（退出码 1），交互模式打印错误 + usage 后返回 REPL。
   理由：不指定 scope 会命中错误 scope 的同名插件。
2. `/plugins list` 未指定 scope 时，获取并展示所有 runtime scope 的插件。
3. `/plugins config` 未指定 scope 时，获取并展示所有 config scope 的配置。
4. 修复 API 层丢弃 scope 的根因：runtime 变更端点按 (scope, 插件名) 精确
   查找，而不是按插件名全局查找。

## 现状问题

- API 的 `PUT /plugins/runtime/{name}/enabled`、`/properties`、
  `POST /plugins/runtime/{name}/upgrade`、`DELETE /plugins/runtime/{name}`
  不声明 scope 查询参数，CLI 传入的 `?scope=...` 被 FastAPI 静默忽略。
- `RuntimeMutationCoordinator._registration(name)` 只按插件名匹配，同名插件
  存在于多个 runtime scope 时命中第一个（错误 scope）。
- 非交互 `plugins runtime set` 不强制 `--scope`（其余变更操作已强制）。
- 交互式 `enable|disable`、`uninstall`、`runtime set` 只检查参数个数，不校验
  scope 格式。
- 交互式 `history`、`rollback` 缺省时静默回退到 api scope
  （`DEFAULT_CONFIG_SCOPE`），可能读到/改到错误 scope 的数据。
- 聚合 list 输出没有 Scope 列，无法得知插件属于哪个 scope，也就无法用
  新的强制 scope 规则去操作它。

## 词汇表

- runtime scope（`langharness_scope` scope 树 + 动态注册的 `scope_id`）：
  `root` / `server` / `ui` / `agent` / `agent:<id>`
- config scope（`PluginConfigStore`，见 API `KNOWN_SCOPES`）：
  `api` / `cli` / `agent:<id>`

## 设计

### 1. 协调器 + 协议层（根因修复）

`src/langharness_plugin/contracts.py` 的 `DynamicPluginManager` 协议，
四个变更方法增加必填 keyword-only 参数：

```python
def set_enabled(self, name: str, enabled: bool, *,
                scope_id: ScopeId) -> PersistedPluginRegistration: ...
def update_properties(self, name: str, properties: dict[str, object], *,
                      scope_id: ScopeId) -> PersistedPluginRegistration: ...
def uninstall(self, name: str, *, scope_id: ScopeId) -> None: ...
def upgrade(self, name: str, *, scope_id: ScopeId) -> PersistedPluginRegistration: ...
```

`src/langharness_plugin/coordinator.py`：

- `_registration(name)` 改为 `_registration(name, scope_id)`，同时匹配
  `registration.descriptor.name == name` 与
  `registration.scope_id == scope_id`；未命中抛 `KeyError`（消息包含
  scope 与 name）。
- 四个变更方法透传 `scope_id`；`install` 不变（body 中已有 `scope_id`）。
- 生产代码调用方只有 API 路由层（已核对），e2e 测试同步更新。

### 2. API 路由层

`src/langharness_api/plugins/routes/plugins.py`：

- 四个 runtime 变更端点增加必填 `scope: str = Query(...)`，先调用新 helper
  `_validate_runtime_scope(scope)`（合法值 `root` / `server` / `ui` /
  `agent` / `agent:<id>`，非法返回 400），再以 `ScopeId(scope)` 调用协调器。
- 未匹配到注册时返回 404，detail 说明 "plugin not found in scope X"
  （KeyError 捕获分支转换）。
- `GET /plugins/runtime` 行为不变（有 scope 过滤、无 scope 聚合所有），
  顺带加 `_validate_runtime_scope` 校验：垃圾 scope 返回 400 而非静默空列表。
- `GET /plugins`、`/plugins/history`、`/plugins/rollback`、`/plugins/install`
  不变（config 层已有 `_validate_scope`）。

### 3. CLI 层（非交互 + 交互）

`src/langharness_cli/plugins/commands/plugins.py`：

统一原则：变更操作缺 scope → 打印
`"Scope is required. Specify …"` 错误 + usage；非交互退出码 1，交互式返回
REPL。scope 格式校验按词汇表分两套：

- runtime 操作（`enable|disable` / `uninstall` / `upgrade` / `runtime set`）：
  `server` / `ui` / `agent` / `agent:<id>` / `root`
- config 操作（`set` / `config enable|disable` / `history` / `rollback`）：
  `api` / `cli` / `agent:<id>`

具体改动：

- 非交互：`runtime set` 补强制 `--scope`；`enable|disable` / `uninstall` /
  `upgrade` 补格式校验；`list` / `config` 无 scope 聚合行为不变。
- 交互式：`enable|disable` / `uninstall` / `runtime set` 补 scope 校验；
  `history` / `rollback` 改为强制 `<scope>` 开头，删除静默回退 api 的逻辑。
  删除死代码：`DEFAULT_CONFIG_SCOPE`、`DEFAULT_RUNTIME_SCOPE` 常量，
  `_scope` / `_runtime_scope` helper，`_plugin_arguments` 的缺省分支。
- `_usage` 文本同步更新（`history <config_scope>`、
  `rollback <config_scope> <version>` 等）。
- `install` 维持现状（已强制 scope，agent_instance 语义由协调器报错）。

### 4. 展示与测试

- 聚合 `list`（无 scope）表格增加 Scope 列（`_runtime_table` 扩展）；
  单 scope 视图不变。聚合 `config` 已有 Scope 列，不动。
- 测试更新/新增：
  - `tests/test_plugin_commands.py`：缺 scope / 非法 scope 报错退出；
    `history` / `rollback` 缺 scope 只打 usage 不发请求；聚合 list 含
    Scope 列。
  - `tests/test_plugin_config_routes.py`：变更端点缺 scope → 422、
    非法 scope → 400、scope 内无此插件 → 404；正常路径带 scope 调用协调器。
  - `tests/test_dynamic_plugin_e2e.py`、`tests/test_runtime_mutation_coordinator.py`：
    调用补 `scope_id`；新增"同名插件注册于两个 scope，只命中指定 scope"用例。
  - `tests/manual_cli_smoke.sh` 若调用这些端点则同步修正。

## 错误处理汇总

| 场景 | 行为 |
| --- | --- |
| CLI 变更操作缺 scope | 错误信息 + usage；非交互退出码 1，交互返回 REPL |
| CLI scope 格式非法 | 同上，信息中列出合法 scope |
| API 缺 scope（Query 必填） | FastAPI 422 |
| API scope 格式非法 | 400 `Unknown runtime scope: X` |
| API (scope, name) 未匹配 | 404 `plugin not found in scope X` |

## 范围外

- `install` 的 scope_id 语义与 agent_instance 校验逻辑不变。
- config 层（`/plugins`、`/history`、`/rollback`）路由逻辑不变。
- `template_system_prompt.py` 等动态插件属性相关改动不在本设计内。
