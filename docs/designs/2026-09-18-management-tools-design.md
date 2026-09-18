# 插件/scope 管理操作包装为 agent 工具设计方案

## 目标

1. 把 `/plugins`（运行时面）与 `/scope` 的操作包装成 LangChain 工具，供
   agent loop 的 LLM 调用（自管理：查看作用域、发现/安装/启停/升级/卸载
   插件、更新运行时属性）。
2. 管理工具本身是一个可动态安装、启停的 `ToolProvider` 插件，**按作用域
   动态决定是否进入 agent loop 的工具集**；开关完全复用现有
   `/plugins install / enable / disable` 机制，loop 重建 graph 后立即生效。
3. 每个工具必须有 **入参约束**（pydantic args_schema + scope 词汇显式
   校验，危险操作强制 confirm 参数）与 **提示词**（description 写明用途、
   使用时机、约束、示例），让 LLM 知道怎么用、何时用。
4. 不含 config 作用域（api/cli）操作与 history/rollback。

## 现状

- agent loop（`langharmess_core/plugins/loop/agent_loop.py`）由 iPOPO 服务
  装配，`ToolProvider` 服务经 scope 链（`agent:<id>` → agent → … → root）
  注入；任何服务 bind/unbind 触发 graph 重建，**工具集本身可动态增减**。
- `/plugins`、`/scope` 是 CLI 交互命令，经 HTTP 调 API，最终落到 server
  进程内的 `RuntimeMutationCoordinator`（注册为 `plugin.dynamic.manager`
  运行时服务，root 作用域，见 `PluginManager.register_runtime_service`）。
  agent loop 同样运行在 server 进程，**工具可以进程内直接绑定
  `DynamicPluginManager` 协议服务**，无需 HTTP。
- 动态插件目录：`langharmess_core/plugin.py` 的 `DYNAMIC_PLUGIN_CATALOG`
  自动生成 `dynamic.core` 包的贡献（target 均为 `agent`），可被
  `/plugins install` 发现并按注册持久化、由 `restore()` 恢复。
- coordinator 的 `install` 对 target `agent_instance` 的贡献会按 scope 后缀
  重命名实例（`name@agent-<id>`）并落到 `agent:<id>` 作用域；对 target
  `agent` 的贡献落 `agent` 作用域。
- scope 词汇校验目前分散在 CLI（`_is_runtime_scope`）与 API
  （`KNOWN_RUNTIME_SCOPES` + `_validate_runtime_scope`）两处，无共享 helper。
- `ToolExport.destructive` 字段已声明但无消费方；本方案不引入全局拦截层，
  危险操作改为**入参级 confirm**。

## 词汇表

- runtime scope：`root` / `server` / `ui` / `agent` / `agent:<id>`
  （`agent:` 后必须非空）。
- confirm token：`DISABLE`（disable_plugin）、`UNINSTALL`
  （uninstall_plugin），`Literal` 精确匹配。

## 设计

### 1. 调用路径：进程内绑定 coordinator

管理插件组件 `@RequiresBest("_dynamic_manager", DynamicPluginManager,
optional=True)`，工具函数直接调用 coordinator 方法；`BindField` 回调用
`ContractGuard` 守卫（现有惯例）。manager 未就绪（非 server 模式）时
`get_tools()` 返回 `[]`。

不采用 HTTP 自调用（server 调自己的 API：事件循环阻塞风险、鉴权配置、
错误映射重复）与 ToolExport 适配器复用（适配器由 coordinator 自己创建，
鸡生蛋；coordinator 不是插件实例，`find_service` 查不到）。

### 2. 新插件 `management-tools`

新文件 `src/langharmess_core/plugins/tools/management.py`（仿
`plugins/tools/workspace.py` 写法）：

- `@ComponentFactory("management-tools-plugin-factory")`
  `@Provides(ToolProvider)`，`plugin.name` = `management-tools-plugin`。
- `get_tools()` 返回 9 个 `StructuredTool`（见 §4），全部
  `StructuredTool.from_function` + pydantic v2 args_schema。
- 工具函数捕获 `RuntimeMutationError / KeyError / ValueError`，统一返回
  `{"error": "<message>"}`，让 LLM 可读后纠正（scope 拼错、插件不存在、
  重复安装等）。

### 3. 注册进动态目录与两种安装形态

`DYNAMIC_PLUGIN_CATALOG` 增加条目：

```python
"management-tools-plugin": (
    "langharmess_core.plugins.tools.management",
    "management-tools-plugin-factory",
    SPEC_TOOL,
),
```

`dynamic_package()` 现有推导会生成贡献
`management-tools-plugin-template`（target `agent`），并额外生成一个
`agent_instance` 贡献 `management-tools-plugin-instance`：

- `management-tools-plugin-template`（target `agent`）：install 后注册名
  `management-tools-plugin-template`，落 `agent` 作用域，**所有** agent
  loop 可见。
- `management-tools-plugin-instance`（target `agent_instance`）：install 时
  scope 必须 `agent:<id>`，注册名按协调器惯例后缀为
  `management-tools-plugin-template@agent-<id>`，仅该 agent 的 loop 可见。

**同 module 防呆**：两个贡献共用同一 module。第三方包在多个作用域安装同一 module
是既有受支持流程（Pelix 对同 module 的 `install_bundle` 去重返回同一 bundle），
但 `dynamic.core` 内两个管理贡献同时安装是纯冗余（agent 已覆盖全部
`agent:<id>`），且卸载其一会连带停掉共享 bundle 上另一个的组件。因此：

- `coordinator.install` 增加前置守卫（仅 `dynamic.core` 包生效）：新注册的
  `descriptor.module` 已被**不同名**的现有注册占用时，抛
  `RuntimeMutationError`（消息说明同 module 二选一），保持事务回滚语义。
  第三方包的同 module 多作用域安装不受影响。
- 文档注明两者二选一（`agent` 已覆盖全部 `agent:<id>`）。

### 4. 工具清单、入参约束与提示词

读（3 个）：

| 工具 | 参数 | 说明 |
| --- | --- | --- |
| `list_scope_tree` | 无 | 文本树（复用 §5 的共享渲染器） |
| `list_runtime_plugins` | `scope: str \| None = None`（可选，缺省聚合所有 scope） | 注册摘要列表：name/scope_id/enabled/status/package_id/contribution_id/specification（仿 API `_registration_payload`，不含内嵌服务对象的 descriptor） |
| `discover_plugins` | 无 | `rescan()` + 已发现包摘要：package_id/version/contribution_id/name/specification/module |

变更（6 个）：

| 工具 | 参数 | 说明 |
| --- | --- | --- |
| `install_plugin` | `package_id`（非空）、`contribution_id`（非空）、`scope`（必填，runtime 词汇） | 只装已发现包；builtin.* 会被拒；装的插件初始 disabled |
| `enable_plugin` | `name`（非空）、`scope`（必填） | 启用后新工具立即进 loop |
| `disable_plugin` | `name`、`scope`、`confirm: Literal["DISABLE"]`（必填） | 组件解绑、状态持久化为 disabled |
| `upgrade_plugin` | `name`、`scope`（必填） | 升到包最新版本 |
| `uninstall_plugin` | `name`、`scope`、`confirm: Literal["UNINSTALL"]`（必填） | 删除持久化状态，不可自动回滚 |
| `update_plugin_properties` | `name`、`scope`、`properties: dict`（非空） | 对应 CLI 的 runtime set |

入参约束实现要点：

- scope 用 pydantic `field_validator` 校验 runtime 词汇并拒绝裸 `agent:`；
  新增共享 helper（§5）后三处共用同一实现。
- `confirm` 用 `Literal` 强制精确 token；description 中写清不传/传错即失败。
- 所有变更工具 scope 必填——延续「变更必须显式 scope」的 CLI 契约，宁可
  报错也不静默命中错误 scope。

提示词（每个工具的 description 固定五要素）：

1. 一句话用途；2. **何时用/何时不用**（先 `discover_plugins` 再
`install_plugin`；enable 后新工具立即进 loop；对未知插件名先
`list_runtime_plugins`；危险操作需 confirm）；3. scope 约束（必须显式、
必须 runtime 词汇）；4. 简短示例；5. 返回格式（注册摘要或
`{"error": ...}`）。示例：

> Install a discovered plugin contribution into a runtime scope. Run
> discover_plugins first to get valid package_id/contribution_id. Scope must
> be one of root/server/ui/agent/`agent:<id>`. Built-in packages cannot be
> installed; installed plugins start disabled — use enable_plugin to
> activate. Returns a registration summary, or {"error": ...}.

### 5. 两个共享 helper 收敛

1. runtime scope 词汇：新增 `langharmess_plugin/validation.py` 的
   `RUNTIME_SCOPES` 与 `is_runtime_scope(value) -> bool`；CLI
   `_is_runtime_scope`、API `_validate_runtime_scope` 与工具 schema
   validator 改为共用。
2. scope 树渲染：把 CLI `commands/scope.py` 的 `_render_tree` 下沉为
   `langharmess_scope` 的 `render_scope_tree(scopes) -> str`；
   `list_scope_tree` 与 CLI 共用（core 不 import cli，避免反向依赖）。

### 6. 动态开关路径（运营视角）

```text
/plugins install dynamic.core management-tools-plugin-template --scope agent
/plugins enable management-tools-plugin-template --scope agent   # loop 重建，工具进集合
/plugins disable management-tools-plugin-template --scope agent  # loop 重建，工具移除
```

- 单 agent：install `management-tools-plugin-instance --scope agent:<id>`，
  enable 时用后缀名 `management-tools-plugin-template@agent-<id>`
  （`list_runtime_plugins` 可见）。
- LLM 可以自己 disable 自己的管理工具（需 confirm）；重新开启由 CLI/API
  兜底。
- 重启后 `restore()` 按持久化状态恢复，生命周期与现有动态插件一致。

### 7. 错误处理

- coordinator 异常在工具内捕获并转 `{"error": ...}`，不抛出——成功与失败
  都走同一条 ToolMessage 通道，返回形状统一，LLM 可读后纠正（scope 拼错、
  插件不存在等）并重试。
- `_rebuild` 现有保护不变：管理插件 bind/unbind 不会让 loop 进入
  ERRONEOUS 状态。

## 测试

沿用项目 TDD + `make check` 门槛（Ruff → mypy → Pyright → import →
pytest，覆盖率 ≥95%）：

- 单元：9 个工具的 schema 校验（scope 词汇、裸 `agent:` 拒绝、confirm
  强制、properties 非空）、工具函数对 fake `DynamicPluginManager` 的调用
  与错误映射、manager 缺失时 `get_tools()` 返回 `[]`、coordinator 同
  module 守卫。
- e2e（真 Pelix + loop，沿用 `tests/test_dynamic_plugin_e2e.py` 模式）：
  安装到 `agent` 作用域后 `loop.describe()` 工具集含 9 个工具名；disable
  后消失；`agent:<id>` 安装仅该 agent 的 loop 可见；同 module 二贡献同时
  安装被守卫拒绝。

## 涉及文件

- 新：`src/langharmess_core/plugins/tools/management.py`（组件 + 9 工具 +
  schemas）
- 改：`src/langharmess_core/plugin.py`（目录条目 + agent_instance 贡献）
- 改：`src/langharmess_plugin/coordinator.py`（同 module 守卫）
- 改：`src/langharmess_plugin/validation.py`（共享 runtime scope helper）
- 改：`src/langharmess_scope/`（`render_scope_tree`）
- 改：`src/langharmess_api/plugins/routes/plugins.py`、
  `src/langharmess_cli/plugins/commands/plugins.py`、
  `src/langharmess_cli/plugins/commands/scope.py`（改用共享 helper）
- 新/改：单元与 e2e 测试
- 改：`README.md`（交互命令章节补充管理工具用法）

## 边界与后续项

- v1 不含 config 作用域（api/cli）操作、history/rollback。
- 同一贡献安装到多个 `agent:<id>`（多 agent 各自独立开关）受同 module
  限制，为后续项；先按「全局 agent 或单 agent 二选一」交付。
- `ToolExport.destructive` 字段本方案不消费，保留给后续第三方包工具导出
  的拦截层设计。
