# 管理工具(插件/scope 操作 → agent 工具)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `/plugins`(运行时面)与 `/scope` 操作包装成 9 个 LangChain 工具,作为可动态安装/启停的 ToolProvider 插件按作用域进入 agent loop,带完整入参约束与提示词。

**Architecture:** 新组件 `ManagementToolsPlugin`(`langharmess_core/plugins/tools/management.py`)经 `@RequiresBest(DynamicPluginManager)` 进程内绑定协调器,9 个 `StructuredTool`(pydantic v2 schema + 五要素 description)直接调用 `RuntimeMutationCoordinator`;插件注册进 `dynamic.core` 目录(agent 目标=全部 loop,agent_instance 目标=单 agent),enable/disable 复用现有协调器并触发 loop 重建。配套两处共享 helper 收敛(scope 词汇、scope 树渲染)与协调器同 module 防呆守卫。

**Tech Stack:** Python 3.13、Pelix/iPOPO、LangChain(langchain-core ≥1.6.2,`StructuredTool.from_function`)、pydantic ≥2.13.5、pytest。

## Global Constraints

- 质量门槛(AGENTS.md):每个 commit 必须过 `make check`(Ruff → mypy → Pyright → clean-process import 检查 → pytest),单元覆盖率 ≥95%(pytest-cov 强制)。
- TDD:先写失败测试,再写最小实现;每个任务独立 commit。
- 生产代码 mypy strict、Pyright standard 不允许全局放宽;e2e 测试文件头已有 `# mypy: ignore-errors` 属既有豁免,不新增豁免。
- 插件间通信只走 Pelix service spec(Protocol),不 import 他方具体类;`langharmess_plugin`/`langharmess_scope` 是框架层,可被 core 依赖。
- 描述符只在 `langharmess_core/plugin.py` 构建;组件实现在 `plugins/<topic>/<name>.py`。
- 文档(docs/、README)用中文,代码/命令用英文;commit message 风格 `feat:` / `refactor:` / `test:` / `docs:`。
- 设计文档:`docs/designs/2026-09-18-management-tools-design.md`(已提交 d1b00ae)。

---

### Task 1: 共享 runtime scope 词汇校验 helper

**Files:**
- Modify: `src/langharmess_plugin/validation.py`(追加 helper)
- Modify: `src/langharmess_cli/plugins/commands/plugins.py:31-44`(改用共享 helper)
- Modify: `src/langharmess_api/plugins/routes/plugins.py:32,342-343`(改用共享 helper)
- Test: `tests/test_validation.py`(追加用例)

**Interfaces:**
- Consumes: 无(第一个任务)。
- Produces: `langharmess_plugin.validation.RUNTIME_SCOPES = ("root", "server", "ui", "agent")`;`is_runtime_scope(value: str) -> bool`——`value in RUNTIME_SCOPES` 或 `value.startswith("agent:") and len(value) > len("agent:")`,拒绝裸 `agent:`。后续 Task 4 的工具 schema、CLI、API 共用。

- [ ] **Step 1: 写失败测试**

在 `tests/test_validation.py` 末尾追加:

```python
@pytest.mark.parametrize(
    "scope", ["root", "server", "ui", "agent", "agent:a", "agent:web-1"]
)
def test_is_runtime_scope_accepts_vocabulary(scope: str) -> None:
    from langharmess_plugin.validation import is_runtime_scope

    assert is_runtime_scope(scope) is True


@pytest.mark.parametrize("scope", ["", "agent:", "api", "cli", "Agent"])
def test_is_runtime_scope_rejects_other_values(scope: str) -> None:
    from langharmess_plugin.validation import is_runtime_scope

    assert is_runtime_scope(scope) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_validation.py -v`
Expected: FAIL with `ImportError: cannot import name 'is_runtime_scope'`

- [ ] **Step 3: 最小实现**

`src/langharmess_plugin/validation.py` 末尾追加:

```python
RUNTIME_SCOPES = ("root", "server", "ui", "agent")


def is_runtime_scope(value: str) -> bool:
    """True for the runtime scope vocabulary: root|server|ui|agent|agent:<id>.

    The bare prefix ``agent:`` is rejected: every mutation must name an
    explicit scope, and ``agent:`` with an empty id is a typo.
    """
    return value in RUNTIME_SCOPES or (
        value.startswith("agent:") and len(value) > len("agent:")
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_validation.py -v`
Expected: PASS

- [ ] **Step 5: CLI 改用共享 helper**

`src/langharmess_cli/plugins/commands/plugins.py`:

删除常量与函数(第 31-44 行的 `RUNTIME_SCOPES` 与 `_is_runtime_scope`,`CONFIG_SCOPES` 与 `_is_config_scope` 保留不动),在 `langharmess_cli.contracts` 导入块之后加一行别名导入:

```python
from langharmess_plugin.validation import is_runtime_scope as _is_runtime_scope
```

文件中其余 8 处 `_is_runtime_scope(` 调用点不变。

- [ ] **Step 6: API 改用共享 helper**

`src/langharmess_api/plugins/routes/plugins.py`:

1. 第 28 行导入改为:

```python
from langharmess_plugin.validation import ContractGuard, is_runtime_scope
```

2. 删除第 32 行 `KNOWN_RUNTIME_SCOPES = ("root", "server", "ui", "agent")`。

3. `_validate_runtime_scope` 方法体替换为:

```python
    def _validate_runtime_scope(self, scope: str) -> None:
        if is_runtime_scope(scope):
            return
        raise http_error(
            400,
            f"Unknown runtime scope: {scope}",
            code="VALIDATION_ERROR",
            error_type="ValidationError",
        )
```

(`_validate_known_scope` 保留,config scope 校验仍在用。)

- [ ] **Step 7: 全量验证**

Run: `make check`
Expected: 全绿(CLI/API 既有测试覆盖词汇行为,行为不变)。

- [ ] **Step 8: Commit**

```bash
git add src/langharmess_plugin/validation.py src/langharmess_cli/plugins/commands/plugins.py src/langharmess_api/plugins/routes/plugins.py tests/test_validation.py
git commit -m "refactor: share runtime scope vocabulary validation between CLI and API"
```

---

### Task 2: scope 树渲染下沉到 langharmess_scope

**Files:**
- Create: `src/langharmess_scope/render.py`
- Modify: `src/langharmess_cli/plugins/commands/scope.py:10-13,77,91-112`(改用共享渲染器)
- Test: `tests/test_scope_render.py`(新建)

**Interfaces:**
- Consumes: 无。
- Produces: `langharmess_scope.render.render_scope_tree(scopes: list[dict[str, Any]]) -> str`——与 CLI 现 `_render_tree` 逐字等价;Task 4 的 `list_scope_tree` 工具复用。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_scope_render.py`:

```python
"""Scope tree text rendering tests."""

from langharmess_scope.render import render_scope_tree


def test_render_scope_tree_orders_roots_and_children() -> None:
    scopes = [
        {"id": "root", "parent_id": None, "name": "root"},
        {"id": "agent", "parent_id": "root", "name": "agent"},
        {"id": "server", "parent_id": "root", "name": "server"},
        {"id": "agent:a", "parent_id": "agent", "name": "A"},
    ]
    assert render_scope_tree(scopes) == (
        "root\n├── agent\n│   └── agent:a\n└── server"
    )


def test_render_scope_tree_handles_empty() -> None:
    assert render_scope_tree([]) == ""


def test_render_scope_tree_sorts_siblings_by_id() -> None:
    scopes = [
        {"id": "root", "parent_id": None, "name": "root"},
        {"id": "z", "parent_id": "root", "name": "z"},
        {"id": "a", "parent_id": "root", "name": "a"},
    ]
    assert render_scope_tree(scopes) == "root\n├── a\n└── z"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_scope_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langharmess_scope.render'`

- [ ] **Step 3: 最小实现**

新建 `src/langharmess_scope/render.py`(从 CLI `_render_tree` 原样迁入):

```python
"""Text rendering for scope trees."""

from __future__ import annotations

from typing import Any


def render_scope_tree(scopes: list[dict[str, Any]]) -> str:
    """Render one indented tree line per scope; children sorted by id."""
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    for scope in scopes:
        by_parent.setdefault(scope.get("parent_id"), []).append(scope)
    lines: list[str] = []

    def visit(parent_id: str | None, prefix: str) -> None:
        children = sorted(
            by_parent.get(parent_id) or [], key=lambda item: str(item["id"])
        )
        for index, child in enumerate(children):
            last = index == len(children) - 1
            lines.append(f"{prefix}{'└── ' if last else '├── '}{child['id']}")
            visit(child["id"], prefix + ("    " if last else "│   "))

    for root in sorted(
        by_parent.get(None) or [], key=lambda item: str(item["id"])
    ):
        lines.append(str(root["id"]))
        visit(root["id"], "")
    return "\n".join(lines)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_scope_render.py -v`
Expected: PASS

- [ ] **Step 5: CLI 接入共享渲染器**

`src/langharmess_cli/plugins/commands/scope.py`:

1. 在 `langharmess_cli.contracts` 导入块之后加:

```python
from langharmess_scope.render import render_scope_tree
```

2. 第 77 行调用改:

```python
        print(render_scope_tree(payload.get("scopes") or []))
```

3. 删除第 91-112 行的 `_render_tree` 函数定义。

- [ ] **Step 6: 全量验证**

Run: `make check`
Expected: 全绿(`tests/test_scope_command.py` 输出行为不变)。

- [ ] **Step 7: Commit**

```bash
git add src/langharmess_scope/render.py src/langharmess_cli/plugins/commands/scope.py tests/test_scope_render.py
git commit -m "refactor: move scope tree rendering into langharmess_scope"
```

---

### Task 3: coordinator 同 module 安装守卫

**Files:**
- Modify: `src/langharmess_plugin/coordinator.py:80-84`(`install` 内插入守卫)
- Test: `tests/test_runtime_mutation_coordinator.py`(追加用例)

**Interfaces:**
- Consumes: `PersistedPluginRegistration.descriptor.module`(Task 1/2 无关)。
- Produces: `coordinator.install(...)` 在「新描述符的 module 已被**不同名**现有注册占用」时抛 `RuntimeMutationError`(消息含 `"one plugin per module"`),不落任何状态;Task 7 的 e2e 与后续安装路径依赖此行为。

- [ ] **Step 1: 写失败测试**

`tests/test_runtime_mutation_coordinator.py`:

1. 导入行 `from langharmess_plugin.coordinator import RuntimeMutationCoordinator` 改为:

```python
from langharmess_plugin.coordinator import (
    RuntimeMutationCoordinator,
    RuntimeMutationError,
)
```

2. 在 `agent_instance_package()` 之后追加 fixture:

```python
def same_module_package() -> PluginPackage:
    return PluginPackage(
        "same.module",
        "1",
        (
            PluginContribution("one", "server", descriptor("one")),
            PluginContribution("two", "server", descriptor("two")),
        ),
    )
```

3. 文件末尾追加测试(本文件的构造 helper 为 `manager()` / `CountingStore` / `coordinator(runtime, store, packages=...)`,`coordinator` 内部已 `rescan`):

```python
def test_install_rejects_a_second_registration_sharing_a_module() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store, packages=(same_module_package(),))

    mutations.install("same.module", "one")

    with pytest.raises(RuntimeMutationError, match="one plugin per module"):
        mutations.install("same.module", "two")


def test_install_allows_same_module_after_uninstall() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store, packages=(same_module_package(),))

    mutations.install("same.module", "one")
    mutations.uninstall("one", scope_id=ScopeId("server"))
    mutations.install("same.module", "two")
    assert [item.descriptor.name for item in mutations.registrations()] == ["two"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_runtime_mutation_coordinator.py -k "second_registration or same_module_after" -v`
Expected: FAIL——`same.module` 的 `two` 被正常安装,`pytest.raises` 不触发;第二个测试的实际注册名与 `["two"]` 不符。

- [ ] **Step 3: 最小实现**

`src/langharmess_plugin/coordinator.py` 的 `install` 方法,在「同名已装」检查之后追加:

```python
            for item in self._registrations:
                if (
                    item.descriptor.name != descriptor.name
                    and item.descriptor.module == descriptor.module
                ):
                    raise RuntimeMutationError(
                        f"Module {descriptor.module!r} is already installed by "
                        f"{item.descriptor.name!r}; one plugin per module"
                    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_runtime_mutation_coordinator.py -v`
Expected: PASS

- [ ] **Step 5: 全量验证**

Run: `make check`
Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add src/langharmess_plugin/coordinator.py tests/test_runtime_mutation_coordinator.py
git commit -m "feat: reject installing a second plugin from an already-installed module"
```

---

### Task 4: management 组件 + 3 个只读工具

**Files:**
- Create: `src/langharmess_core/plugins/tools/management.py`(组件骨架 + schemas + 只读工具)
- Test: `tests/test_management_tools.py`(新建)

**Interfaces:**
- Consumes: `is_runtime_scope`(Task 1)、`render_scope_tree`(Task 2)、`DynamicPluginManager` 协议、`ContractGuard`。
- Produces(本文件,Task 5 复用):
  - `SCOPE_HELP: str`、`NoArgs(BaseModel)`、`RuntimeScopeArgs(BaseModel)`(scope 必填 + validator)、`ListRuntimePluginsArgs(BaseModel)`(scope 可选 + validator)
  - `_registration_summary(registration: Any) -> dict[str, Any]`(键:name/package_id/contribution_id/version/scope_id/enabled/status/specification)
  - `_discovered_summary(package: Any) -> dict[str, Any]`(键:package_id/version/contributions[id/name/target/module/specification])
  - `_guard(action: Callable[[], Any]) -> dict[str, Any]`(捕获 KeyError/ValueError/RuntimeError → `{"error": str}`)
  - `ManagementToolsPlugin`(factory `management-tools-plugin-factory`,`@RequiresBest("_dynamic_manager", DynamicPluginManager, optional=True, immediate_rebind=True)`);`get_tools()` 在 manager 缺失时返回 `[]`,本任务返回 3 个工具:`list_scope_tree`、`list_runtime_plugins`、`discover_plugins`。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_management_tools.py`:

```python
"""Unit tests for the management tools plugin."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from langharmess_core.plugins.tools.management import ManagementToolsPlugin
from langharmess_scope import Scope, ScopeId

READ_TOOLS = {"list_scope_tree", "list_runtime_plugins", "discover_plugins"}


def _registration(name: str = "demo-plugin", scope_id: str = "agent") -> Any:
    return SimpleNamespace(
        package_id="dynamic.core",
        contribution_id="demo-template",
        package_version="1.0.0",
        scope_id=ScopeId(scope_id),
        enabled=True,
        status="installed",
        descriptor=SimpleNamespace(
            name=name,
            module="langharmess_core.plugins.tools.demo",
            specification="agent.plugin.tools",
        ),
    )


class FakeManager:
    def __init__(self) -> None:
        self.rescan_calls = 0
        self.registrations_ = [
            _registration(),
            _registration(name="other-plugin", scope_id="server"),
        ]
        self.scopes_ = (
            Scope(ScopeId("root"), None, "root"),
            Scope(ScopeId("agent"), ScopeId("root"), "agent"),
            Scope(ScopeId("agent:a"), ScopeId("agent"), "A"),
        )
        self.discovered_ = [
            SimpleNamespace(
                id="dynamic.core",
                version="1.0.0",
                contributions=[
                    SimpleNamespace(
                        id="demo-template",
                        descriptor=SimpleNamespace(
                            name="demo-template",
                            module="langharmess_core.plugins.tools.demo",
                            specification="agent.plugin.tools",
                        ),
                        target="agent",
                    )
                ],
            )
        ]

    def scopes(self) -> tuple[Scope, ...]:
        return self.scopes_

    def registrations(self) -> list[Any]:
        return self.registrations_

    def rescan(self) -> Any:
        self.rescan_calls += 1
        return SimpleNamespace(packages=(), failures=())

    def discovered(self) -> list[Any]:
        return self.discovered_


def _plugin(manager: FakeManager) -> ManagementToolsPlugin:
    plugin = ManagementToolsPlugin()
    plugin._dynamic_manager = manager
    return plugin


def _tools(plugin: ManagementToolsPlugin) -> dict[str, Any]:
    return {tool.name: tool for tool in plugin.get_tools()}


def test_get_tools_empty_without_manager() -> None:
    assert ManagementToolsPlugin().get_tools() == []


def test_get_tools_exposes_read_tools() -> None:
    assert set(_tools(_plugin(FakeManager()))) == READ_TOOLS


def test_list_scope_tree_renders_tree() -> None:
    tool = _tools(_plugin(FakeManager()))["list_scope_tree"]
    assert tool.invoke({}) == {
        "scope_tree": "root\n└── agent\n    └── agent:a"
    }


def test_list_runtime_plugins_aggregates_all_scopes() -> None:
    tool = _tools(_plugin(FakeManager()))["list_runtime_plugins"]
    result = tool.invoke({})
    assert [item["name"] for item in result["plugins"]] == [
        "demo-plugin",
        "other-plugin",
    ]


def test_list_runtime_plugins_filters_by_scope() -> None:
    tool = _tools(_plugin(FakeManager()))["list_runtime_plugins"]
    result = tool.invoke({"scope": "server"})
    assert [item["name"] for item in result["plugins"]] == ["other-plugin"]
    assert result["plugins"][0]["scope_id"] == "server"


def test_list_runtime_plugins_rejects_bare_agent_prefix() -> None:
    from pydantic import ValidationError

    tool = _tools(_plugin(FakeManager()))["list_runtime_plugins"]
    with pytest.raises(ValidationError):
        tool.invoke({"scope": "agent:"})


def test_discover_plugins_rescans_and_lists() -> None:
    manager = FakeManager()
    tool = _tools(_plugin(manager))["discover_plugins"]
    result = tool.invoke({})
    assert manager.rescan_calls == 1
    assert result["packages"][0]["package_id"] == "dynamic.core"
    assert result["packages"][0]["contributions"][0]["id"] == "demo-template"
```

(文件头补 `import pytest`。)

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_management_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langharmess_core.plugins.tools.management'`

- [ ] **Step 3: 最小实现**

新建 `src/langharmess_core/plugins/tools/management.py`:

```python
"""LangChain tools wrapping the runtime plugin-management coordinator."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.tools import StructuredTool
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Property,
    Provides,
    RequiresBest,
    UnbindField,
)
from pydantic import BaseModel, Field, field_validator

from langharmess_core.contracts import ToolProvider
from langharmess_plugin.contracts import DynamicPluginManager
from langharmess_plugin.validation import ContractGuard, is_runtime_scope
from langharmess_scope import ScopeId
from langharmess_scope.render import render_scope_tree

SCOPE_HELP = (
    "Explicit runtime scope: root, server, ui, agent, or agent:<id>. "
    "The bare prefix 'agent:' is rejected."
)


class NoArgs(BaseModel):
    """Empty schema for parameterless tools."""


class RuntimeScopeArgs(BaseModel):
    """Base schema requiring an explicit, valid runtime scope."""

    scope: str = Field(description=SCOPE_HELP)

    @field_validator("scope")
    @classmethod
    def _validate_scope(cls, value: str) -> str:
        if not is_runtime_scope(value):
            raise ValueError(f"Unknown runtime scope: {value!r}")
        return value


class ListRuntimePluginsArgs(BaseModel):
    """Optional scope filter; omit to aggregate every runtime scope."""

    scope: str | None = Field(
        default=None, description=f"Optional filter. {SCOPE_HELP}"
    )

    @field_validator("scope")
    @classmethod
    def _validate_scope(cls, value: str | None) -> str | None:
        if value is not None and not is_runtime_scope(value):
            raise ValueError(f"Unknown runtime scope: {value!r}")
        return value


def _registration_summary(registration: Any) -> dict[str, Any]:
    """Safe registration view; never serializes embedded service objects."""
    return {
        "name": registration.descriptor.name,
        "package_id": registration.package_id,
        "contribution_id": registration.contribution_id,
        "version": registration.package_version,
        "scope_id": str(registration.scope_id),
        "enabled": registration.enabled,
        "status": registration.status,
        "specification": registration.descriptor.specification,
    }


def _discovered_summary(package: Any) -> dict[str, Any]:
    return {
        "package_id": package.id,
        "version": package.version,
        "contributions": [
            {
                "id": item.id,
                "name": item.descriptor.name,
                "target": item.target,
                "module": item.descriptor.module,
                "specification": item.descriptor.specification,
            }
            for item in package.contributions
        ],
    }


def _guard(action: Callable[[], Any]) -> dict[str, Any]:
    """Run a mutation and map coordinator errors to a readable dict."""
    try:
        return action()
    except (KeyError, ValueError, RuntimeError) as exc:
        return {"error": str(exc)}


@ComponentFactory("management-tools-plugin-factory")
@Provides(ToolProvider)
@Property("_plugin_name", "plugin.name", "management-tools-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@RequiresBest(
    "_dynamic_manager", DynamicPluginManager, optional=True, immediate_rebind=True
)
class ManagementToolsPlugin:
    """Exposes runtime plugin-management operations as LangChain tools."""

    def __init__(self) -> None:
        self._plugin_name = "management-tools-plugin"
        self._plugin_version = "1.0.0"
        self._dynamic_manager: Any = None
        self._guard = ContractGuard(self, "_dynamic_manager", DynamicPluginManager)

    @BindField("_dynamic_manager", if_valid=True)
    def _on_manager_bind(self, field: str, service: Any, reference: Any) -> None:
        if not self._guard.admit(service):
            return

    @UnbindField("_dynamic_manager")
    def _on_manager_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._guard.release(service)

    def get_tools(self) -> list[Any]:
        manager = self._dynamic_manager
        if manager is None:
            return []
        return [
            self._scope_tree_tool(manager),
            self._list_tool(manager),
            self._discover_tool(manager),
        ]

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}

    @staticmethod
    def _scope_tree_tool(manager: Any) -> StructuredTool:
        def list_scope_tree() -> dict[str, Any]:
            scopes = [
                {
                    "id": str(scope.id),
                    "parent_id": (
                        str(scope.parent_id)
                        if scope.parent_id is not None
                        else None
                    ),
                    "name": scope.name,
                }
                for scope in manager.scopes()
            ]
            return {"scope_tree": render_scope_tree(scopes)}

        return StructuredTool.from_function(
            func=list_scope_tree,
            name="list_scope_tree",
            description=(
                "Show the runtime scope tree (root/server/ui/agent/"
                "agent:<id>) with parent-child structure. Use it to "
                "understand scope topology before targeting plugin "
                "operations, because every plugin mutation requires an "
                "explicit scope. Returns {\"scope_tree\": <text tree>}, "
                "or {\"error\": ...}."
            ),
            args_schema=NoArgs,
        )

    @staticmethod
    def _list_tool(manager: Any) -> StructuredTool:
        def list_runtime_plugins(scope: str | None = None) -> dict[str, Any]:
            registrations = manager.registrations()
            if scope is not None:
                registrations = [
                    item for item in registrations if str(item.scope_id) == scope
                ]
            return {
                "plugins": [_registration_summary(item) for item in registrations]
            }

        return StructuredTool.from_function(
            func=list_runtime_plugins,
            name="list_runtime_plugins",
            description=(
                "List installed runtime plugins, optionally filtered by "
                "scope (omit to aggregate every runtime scope). Use it "
                "before enable/disable/upgrade/uninstall to learn the exact "
                "registered plugin names and scopes, because mutations "
                "match by (name, scope). Returns {\"plugins\": [{name, "
                "scope_id, enabled, status, package_id, contribution_id, "
                "specification}]}, or {\"error\": ...}."
            ),
            args_schema=ListRuntimePluginsArgs,
        )

    @staticmethod
    def _discover_tool(manager: Any) -> StructuredTool:
        def discover_plugins() -> dict[str, Any]:
            manager.rescan()
            return {
                "packages": [
                    _discovered_summary(item) for item in manager.discovered()
                ]
            }

        return StructuredTool.from_function(
            func=discover_plugins,
            name="discover_plugins",
            description=(
                "Rescan the plugin catalog and list discoverable packages "
                "with their contributions. Always run this before "
                "install_plugin to obtain valid package_id/contribution_id "
                "pairs. Returns {\"packages\": [{package_id, version, "
                "contributions: [{id, name, target, module, "
                "specification}]}]}, or {\"error\": ...}."
            ),
            args_schema=NoArgs,
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_management_tools.py -v`
Expected: PASS

- [ ] **Step 5: 全量验证**

Run: `make check`
Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add src/langharmess_core/plugins/tools/management.py tests/test_management_tools.py
git commit -m "feat: add management tools plugin with scope/plugin read tools"
```

---

### Task 5: 6 个运行时变更工具 + confirm 约束

**Files:**
- Modify: `src/langharmess_core/plugins/tools/management.py`(追加 schemas 与 6 个工具,`get_tools` 扩到 9 个)
- Test: `tests/test_management_tools.py`(追加用例,并更新 Task 4 的 3 工具断言)

**Interfaces:**
- Consumes: Task 4 全部 Produces(组件、`RuntimeScopeArgs`、`_registration_summary`、`_guard`、`ScopeId`)。
- Produces:
  - `InstallPluginArgs`(package_id、contribution_id 非空 + scope)、`NameScopeArgs`(name 非空 + scope)、`DisablePluginArgs`(name/scope/`confirm: Literal["DISABLE"]`)、`UninstallPluginArgs`(name/scope/`confirm: Literal["UNINSTALL"]`)、`UpdatePropertiesArgs`(name/scope/properties 非空 dict)
  - 最终工具名全集(供 Task 6/7 引用):`list_scope_tree`、`list_runtime_plugins`、`discover_plugins`、`install_plugin`、`enable_plugin`、`disable_plugin`、`upgrade_plugin`、`uninstall_plugin`、`update_plugin_properties`

- [ ] **Step 1: 写失败测试**

`tests/test_management_tools.py` 追加(文件头补 `from langharmess_plugin.coordinator import RuntimeMutationError`):

```python
ALL_TOOLS = READ_TOOLS | {
    "install_plugin",
    "enable_plugin",
    "disable_plugin",
    "upgrade_plugin",
    "uninstall_plugin",
    "update_plugin_properties",
}


class MutatingManager(FakeManager):
    def __init__(self) -> None:
        super().__init__()
        self.installed: list[tuple[str, str, str]] = []
        self.enabled_calls: list[tuple[str, bool, str]] = []
        self.uninstalled: list[tuple[str, str]] = []
        self.upgraded: list[tuple[str, str]] = []
        self.properties_calls: list[tuple[str, dict[str, Any], str]] = []

    def install(
        self, package_id: str, contribution_id: str, *, scope_id: ScopeId | None = None
    ) -> Any:
        self.installed.append((package_id, contribution_id, str(scope_id)))
        return _registration()

    def set_enabled(self, name: str, enabled: bool, *, scope_id: ScopeId) -> Any:
        self.enabled_calls.append((name, enabled, str(scope_id)))
        return _registration(name=name, scope_id=str(scope_id))

    def update_properties(
        self, name: str, properties: dict[str, object], *, scope_id: ScopeId
    ) -> Any:
        self.properties_calls.append((name, dict(properties), str(scope_id)))
        return _registration(name=name, scope_id=str(scope_id))

    def upgrade(self, name: str, *, scope_id: ScopeId) -> Any:
        self.upgraded.append((name, str(scope_id)))
        return _registration(name=name, scope_id=str(scope_id))

    def uninstall(self, name: str, *, scope_id: ScopeId) -> None:
        self.uninstalled.append((name, str(scope_id)))


class RaisingManager(MutatingManager):
    def install(
        self, package_id: str, contribution_id: str, *, scope_id: ScopeId | None = None
    ) -> Any:
        raise RuntimeMutationError("Plugin is already installed: demo-plugin")


def test_get_tools_exposes_all_nine_tools() -> None:
    assert set(_tools(_plugin(MutatingManager()))) == ALL_TOOLS


def test_install_delegates_and_summarizes() -> None:
    manager = MutatingManager()
    tool = _tools(_plugin(manager))["install_plugin"]
    result = tool.invoke(
        {
            "package_id": "dynamic.core",
            "contribution_id": "demo-template",
            "scope": "agent:a",
        }
    )
    assert manager.installed == [("dynamic.core", "demo-template", "agent:a")]
    assert result["name"] == "demo-plugin"
    assert result["scope_id"] == "agent"


def test_install_requires_valid_scope() -> None:
    from pydantic import ValidationError

    tool = _tools(_plugin(MutatingManager()))["install_plugin"]
    with pytest.raises(ValidationError):
        tool.invoke(
            {"package_id": "p", "contribution_id": "c", "scope": "api"}
        )


def test_enable_delegates() -> None:
    manager = MutatingManager()
    tool = _tools(_plugin(manager))["enable_plugin"]
    result = tool.invoke({"name": "demo-plugin", "scope": "agent"})
    assert manager.enabled_calls == [("demo-plugin", True, "agent")]
    assert result["enabled"] is True


def test_disable_requires_exact_confirm_token() -> None:
    from pydantic import ValidationError

    manager = MutatingManager()
    tool = _tools(_plugin(manager))["disable_plugin"]
    with pytest.raises(ValidationError):
        tool.invoke({"name": "demo-plugin", "scope": "agent"})
    with pytest.raises(ValidationError):
        tool.invoke(
            {"name": "demo-plugin", "scope": "agent", "confirm": "DISABLE-IT"}
        )
    result = tool.invoke(
        {"name": "demo-plugin", "scope": "agent", "confirm": "DISABLE"}
    )
    assert manager.enabled_calls == [("demo-plugin", False, "agent")]
    assert result["enabled"] is False


def test_upgrade_delegates() -> None:
    manager = MutatingManager()
    tool = _tools(_plugin(manager))["upgrade_plugin"]
    tool.invoke({"name": "demo-plugin", "scope": "agent"})
    assert manager.upgraded == [("demo-plugin", "agent")]


def test_uninstall_requires_exact_confirm_token() -> None:
    from pydantic import ValidationError

    manager = MutatingManager()
    tool = _tools(_plugin(manager))["uninstall_plugin"]
    with pytest.raises(ValidationError):
        tool.invoke({"name": "demo-plugin", "scope": "agent"})
    result = tool.invoke(
        {"name": "demo-plugin", "scope": "agent", "confirm": "UNINSTALL"}
    )
    assert manager.uninstalled == [("demo-plugin", "agent")]
    assert result == {"removed": True}


def test_update_properties_delegates_and_requires_nonempty() -> None:
    from pydantic import ValidationError

    manager = MutatingManager()
    tool = _tools(_plugin(manager))["update_plugin_properties"]
    with pytest.raises(ValidationError):
        tool.invoke({"name": "demo-plugin", "scope": "agent", "properties": {}})
    result = tool.invoke(
        {
            "name": "demo-plugin",
            "scope": "agent",
            "properties": {"plugin.timeout": 5},
        }
    )
    assert manager.properties_calls == [
        ("demo-plugin", {"plugin.timeout": 5}, "agent")
    ]
    assert result["name"] == "demo-plugin"


def test_coordinator_errors_map_to_error_dicts() -> None:
    tool = _tools(_plugin(RaisingManager()))["install_plugin"]
    result = tool.invoke(
        {"package_id": "p", "contribution_id": "c", "scope": "agent"}
    )
    assert result == {"error": "Plugin is already installed: demo-plugin"}
```

并把 Task 4 的 `test_get_tools_exposes_read_tools` 改为:

```python
def test_get_tools_exposes_read_tools_without_mutations() -> None:
    """MutatingManager 尚未实现变更工具前,先用 FakeManager 断言只读子集。"""
    assert READ_TOOLS <= set(_tools(_plugin(FakeManager())))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_management_tools.py -v`
Expected: FAIL——`set(_tools(...)) == ALL_TOOLS` 仅 3 个工具;install/disable 等 `KeyError`(工具名不在 `_tools` 返回里)。

- [ ] **Step 3: 最小实现**

`management.py` 的 `from typing import Any` 改为 `from typing import Any, Literal`。

在 `ListRuntimePluginsArgs` 之后追加 schemas:

```python
class InstallPluginArgs(RuntimeScopeArgs):
    package_id: str = Field(
        min_length=1, description="Package id from discover_plugins."
    )
    contribution_id: str = Field(
        min_length=1, description="Contribution id from discover_plugins."
    )


class NameScopeArgs(RuntimeScopeArgs):
    name: str = Field(
        min_length=1,
        description="Exact registered plugin name from list_runtime_plugins.",
    )


class DisablePluginArgs(NameScopeArgs):
    confirm: Literal["DISABLE"] = Field(
        description="Must be the exact string 'DISABLE'."
    )


class UninstallPluginArgs(NameScopeArgs):
    confirm: Literal["UNINSTALL"] = Field(
        description="Must be the exact string 'UNINSTALL'."
    )


class UpdatePropertiesArgs(NameScopeArgs):
    properties: dict[str, Any] = Field(
        min_length=1, description="Non-empty mapping of property overrides."
    )
```

`get_tools` 返回值扩为 9 个:

```python
        return [
            self._scope_tree_tool(manager),
            self._list_tool(manager),
            self._discover_tool(manager),
            self._install_tool(manager),
            self._enable_tool(manager),
            self._disable_tool(manager),
            self._upgrade_tool(manager),
            self._uninstall_tool(manager),
            self._properties_tool(manager),
        ]
```

类内追加 6 个工厂方法(接在 `_discover_tool` 之后):

```python
    @staticmethod
    def _install_tool(manager: Any) -> StructuredTool:
        def install_plugin(
            package_id: str, contribution_id: str, scope: str
        ) -> dict[str, Any]:
            return _guard(
                lambda: _registration_summary(
                    manager.install(
                        package_id,
                        contribution_id,
                        scope_id=ScopeId(scope),
                    )
                )
            )

        return StructuredTool.from_function(
            func=install_plugin,
            name="install_plugin",
            description=(
                "Install a discovered plugin contribution into a runtime "
                "scope. Run discover_plugins first to get valid "
                "package_id/contribution_id. Scope must be one of "
                "root/server/ui/agent/agent:<id> and is required — omitting "
                "or misspelling it fails instead of targeting the wrong "
                "scope. Built-in packages cannot be installed. Installed "
                "plugins start disabled; use enable_plugin to activate. "
                "Example: install_plugin(package_id='dynamic.core', "
                "contribution_id='management-tools-plugin-template', "
                "scope='agent'). Returns a registration summary, or "
                "{\"error\": ...}."
            ),
            args_schema=InstallPluginArgs,
        )

    @staticmethod
    def _enable_tool(manager: Any) -> StructuredTool:
        def enable_plugin(name: str, scope: str) -> dict[str, Any]:
            return _guard(
                lambda: _registration_summary(
                    manager.set_enabled(name, True, scope_id=ScopeId(scope))
                )
            )

        return StructuredTool.from_function(
            func=enable_plugin,
            name="enable_plugin",
            description=(
                "Enable a disabled runtime plugin in an explicit scope, "
                "activating its components immediately — tools it provides "
                "become available right away. name must be the exact "
                "registered plugin name from list_runtime_plugins. Returns "
                "a registration summary, or {\"error\": ...}."
            ),
            args_schema=NameScopeArgs,
        )

    @staticmethod
    def _disable_tool(manager: Any) -> StructuredTool:
        def disable_plugin(
            name: str, scope: str, confirm: str
        ) -> dict[str, Any]:
            return _guard(
                lambda: _registration_summary(
                    manager.set_enabled(name, False, scope_id=ScopeId(scope))
                )
            )

        return StructuredTool.from_function(
            func=disable_plugin,
            name="disable_plugin",
            description=(
                "Disable a runtime plugin in an explicit scope, unbinding "
                "its components immediately — its tools disappear from the "
                "agent loop. This includes disabling this management plugin "
                "itself; do that only when the user asked for it, because "
                "you cannot re-enable it afterwards. You MUST pass "
                "confirm='DISABLE' exactly or the call fails. Returns a "
                "registration summary, or {\"error\": ...}."
            ),
            args_schema=DisablePluginArgs,
        )

    @staticmethod
    def _upgrade_tool(manager: Any) -> StructuredTool:
        def upgrade_plugin(name: str, scope: str) -> dict[str, Any]:
            return _guard(
                lambda: _registration_summary(
                    manager.upgrade(name, scope_id=ScopeId(scope))
                )
            )

        return StructuredTool.from_function(
            func=upgrade_plugin,
            name="upgrade_plugin",
            description=(
                "Upgrade an installed runtime plugin in an explicit scope "
                "to the latest discovered package version. Use "
                "list_runtime_plugins first to confirm the status is "
                "'upgrade_available'. Returns a registration summary, or "
                "{\"error\": ...}."
            ),
            args_schema=NameScopeArgs,
        )

    @staticmethod
    def _uninstall_tool(manager: Any) -> StructuredTool:
        def uninstall_plugin(
            name: str, scope: str, confirm: str
        ) -> dict[str, Any]:
            def action() -> dict[str, Any]:
                manager.uninstall(name, scope_id=ScopeId(scope))
                return {"removed": True}

            return _guard(action)

        return StructuredTool.from_function(
            func=uninstall_plugin,
            name="uninstall_plugin",
            description=(
                "Permanently uninstall a runtime plugin from an explicit "
                "scope and delete its persisted registration; this cannot "
                "be undone automatically. Use disable_plugin instead when "
                "you only want to pause it. You MUST pass "
                "confirm='UNINSTALL' exactly or the call fails. Returns "
                "{\"removed\": true}, or {\"error\": ...}."
            ),
            args_schema=UninstallPluginArgs,
        )

    @staticmethod
    def _properties_tool(manager: Any) -> StructuredTool:
        def update_plugin_properties(
            name: str, scope: str, properties: dict[str, Any]
        ) -> dict[str, Any]:
            return _guard(
                lambda: _registration_summary(
                    manager.update_properties(
                        name, properties, scope_id=ScopeId(scope)
                    )
                )
            )

        return StructuredTool.from_function(
            func=update_plugin_properties,
            name="update_plugin_properties",
            description=(
                "Replace or add runtime properties of an installed plugin "
                "instance in an explicit scope (the runtime 'set' "
                "operation). properties must be a non-empty mapping of "
                "key/value pairs. Use list_runtime_plugins first for the "
                "exact registered name. Returns a registration summary, or "
                "{\"error\": ...}."
            ),
            args_schema=UpdatePropertiesArgs,
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_management_tools.py -v`
Expected: PASS

- [ ] **Step 5: 全量验证**

Run: `make check`
Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add src/langharmess_core/plugins/tools/management.py tests/test_management_tools.py
git commit -m "feat: expose runtime plugin mutations as management tools"
```

---

### Task 6: dynamic.core 目录注册(agent + agent_instance 两贡献)

**Files:**
- Modify: `src/langharmess_core/plugin.py:55-121,386-397`(目录条目 + `dynamic_package` 额外贡献)
- Test: `tests/test_core_descriptors.py:30-46,147-160`(更新期望集合与 target 断言)

**Interfaces:**
- Consumes: Task 5 的组件 module/factory 名(字符串引用,不 import)。
- Produces:`DYNAMIC_PLUGIN_CATALOG["management-tools-plugin"] = ("langharmess_core.plugins.tools.management", "management-tools-plugin-factory", SPEC_TOOL)`;`dynamic.core` 贡献 id:`management-tools-plugin-template`(target `agent`,注册名同名)与 `management-tools-plugin-instance`(target `agent_instance`,注册名 `management-tools-plugin-template@agent-<id>`)。

- [ ] **Step 1: 写失败测试**

`tests/test_core_descriptors.py`:

1. `EXPECTED_DYNAMIC_CONTRIBUTIONS` 集合在 `"interrupt-before-plugin-template"` 之后插入两行:

```python
        "management-tools-plugin-instance",
        "management-tools-plugin-template",
```

2. `test_dynamic_templates_install_without_instantiating` 改为:

```python
def test_dynamic_templates_install_without_instantiating() -> None:
    for contribution in dynamic_package().contributions:
        descriptor = contribution.descriptor
        if contribution.id == "management-tools-plugin-instance":
            assert contribution.target == "agent_instance"
        else:
            assert contribution.target == "agent"
        assert descriptor.name.endswith("-template")
        assert descriptor.enabled is False
        assert descriptor.instance == descriptor.name
        assert descriptor.scope == "agent"
        assert descriptor.scope_parent == "root"
        assert descriptor.module.startswith("langharmess_core.plugins.")
        assert descriptor.factory.endswith("-factory")
        assert descriptor.specification.startswith("agent.plugin.")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_core_descriptors.py -v`
Expected: FAIL——`dynamic_ids == EXPECTED_DYNAMIC_CONTRIBUTIONS` 多出/缺少元素(实测:实际集合缺少两个新 id,断言失败)。

- [ ] **Step 3: 最小实现**

`src/langharmess_core/plugin.py`:

1. `DYNAMIC_PLUGIN_CATALOG` 在 `"interrupt-before-plugin"` 条目之后插入:

```python
    "management-tools-plugin": (
        "langharmess_core.plugins.tools.management",
        "management-tools-plugin-factory",
        SPEC_TOOL,
    ),
```

2. `dynamic_package()` 改为:

```python
def dynamic_package() -> PluginPackage:
    """Describe the core plugins installable at runtime, beyond the built-in set."""
    contributions = [
        PluginContribution(
            f"{plugin}-template", "agent", dynamic_template_descriptor(plugin)
        )
        for plugin in DYNAMIC_PLUGIN_CATALOG
    ]
    contributions.append(
        PluginContribution(
            "management-tools-plugin-instance",
            "agent_instance",
            dynamic_template_descriptor("management-tools-plugin"),
        )
    )
    return PluginPackage(
        id="dynamic.core",
        version="1.0.0",
        contributions=tuple(contributions),
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_core_descriptors.py tests/test_plugin_discovery.py -v`
Expected: PASS

- [ ] **Step 5: 全量验证**

Run: `make check`
Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add src/langharmess_core/plugin.py tests/test_core_descriptors.py
git commit -m "feat: register management tools in the dynamic catalog"
```

---

### Task 7: e2e——安装/启停可见性与 loop 视角

**Files:**
- Test: `tests/test_dynamic_plugin_e2e.py`(追加 3 个 e2e 用例)

**Interfaces:**
- Consumes: Task 3 守卫、Task 4/5 的 9 个工具名、Task 6 的贡献 id 与注册名;既有 e2e helper(`make_manager`/`install_templates`/`tool_names`/`EntryPoint`/`InMemoryRuntimeStateStore`)。
- Produces: 无对外接口,仅测试。

- [ ] **Step 1: 写失败测试**

`tests/test_dynamic_plugin_e2e.py`:

1. 导入调整:第 12 行现有
   `from langharmess_plugin.coordinator import RuntimeMutationCoordinator`
   替换为:

```python
from langharmess_plugin.coordinator import (
    RuntimeMutationCoordinator,
    RuntimeMutationError,
)
```

   并在头部追加其余导入:

```python
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from langharmess_core.contracts import SPEC_AGENT_LOOP, SPEC_LLM, SPEC_TOOL
from langharmess_core.plugin import (
    agent_loop_descriptor,
    agent_loop_template_descriptor,
    dynamic_package,
)
from langharmess_plugin.contracts import DynamicPluginManager
```

2. 在 `tool_names` 之后追加常量与 helper:

```python
MANAGEMENT_TOOLS = {
    "list_scope_tree",
    "list_runtime_plugins",
    "discover_plugins",
    "install_plugin",
    "enable_plugin",
    "disable_plugin",
    "upgrade_plugin",
    "uninstall_plugin",
    "update_plugin_properties",
}


class StaticModel(BaseChatModel):
    response: str = "ok"

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=self.response))]
        )

    @property
    def _llm_type(self) -> str:
        return "static-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> StaticModel:
        return self


def make_loop_manager() -> PluginManager:
    manager = PluginManager(
        PluginRegistry(
            [
                PluginDescriptor(
                    name="tools-template",
                    version="1.0.0",
                    module="langharmess_core.plugins.tools.tools",
                    factory="tools-plugin-factory",
                    instance="tools-template",
                    specification=SPEC_TOOL,
                    enabled=False,
                ),
                PluginDescriptor(
                    name="llm-template",
                    version="1.0.0",
                    module="langharmess_core.plugins.llm.llm",
                    factory="llm-plugin-factory",
                    instance="llm-template",
                    specification=SPEC_LLM,
                    enabled=False,
                ),
                tool_export_adapter_template_descriptor(),
                agent_loop_template_descriptor(),
            ]
        )
    )
    manager.start()
    return manager


def materialize_loop(manager: PluginManager) -> None:
    scope = ScopeId("agent:a")
    manager.instantiate_instance(
        PluginDescriptor(
            name="llm-a",
            version="1.0.0",
            module="langharmess_core.plugins.llm.llm",
            factory="llm-plugin-factory",
            instance="llm-a",
            specification=SPEC_LLM,
            properties={
                "plugin.model.instance": StaticModel(),
                "plugin.agent_id": "a",
            },
        ),
        scope_id=scope,
        plugin_key="llm",
    )
    manager.instantiate_instance(
        agent_loop_descriptor(
            "a",
            [SPEC_LLM, SPEC_TOOL],
            visibility_filter=manager.scope_filter(scope),
        ),
        scope_id=scope,
        plugin_key="agent-loop",
    )


def loop_tool_names(manager: PluginManager) -> list[str]:
    loops = manager.get_services(SPEC_AGENT_LOOP)
    assert len(loops) == 1
    return [str(tool) for tool in loops[0].describe()["tools"]]


def management_discovery() -> PluginDiscovery:
    return PluginDiscovery(lambda: [EntryPoint(dynamic_package(), "dynamic-core")])
```

3. 文件末尾追加 3 个测试:

```python
def test_management_tools_install_enable_disable_visibility() -> None:
    manager = make_manager()
    try:
        install_templates(manager)
        store = InMemoryRuntimeStateStore()
        coordinator = RuntimeMutationCoordinator(
            manager, store, management_discovery()
        )
        manager.register_runtime_service(DynamicPluginManager, coordinator)
        coordinator.rescan()

        registration = coordinator.install(
            "dynamic.core",
            "management-tools-plugin-template",
            scope_id=ScopeId("agent"),
        )
        assert registration.descriptor.name == "management-tools-plugin-template"
        assert MANAGEMENT_TOOLS.isdisjoint(tool_names(manager, "agent"))

        enabled = coordinator.set_enabled(
            "management-tools-plugin-template", True, scope_id=ScopeId("agent")
        )
        assert enabled.enabled is True
        assert MANAGEMENT_TOOLS <= set(tool_names(manager, "agent"))
        assert MANAGEMENT_TOOLS.isdisjoint(tool_names(manager, "ui"))

        disabled = coordinator.set_enabled(
            "management-tools-plugin-template", False, scope_id=ScopeId("agent")
        )
        assert disabled.enabled is False
        assert MANAGEMENT_TOOLS.isdisjoint(tool_names(manager, "agent"))
    finally:
        manager.stop()


def test_management_tools_agent_instance_and_module_guard() -> None:
    manager = make_manager()
    try:
        install_templates(manager)
        store = InMemoryRuntimeStateStore()
        coordinator = RuntimeMutationCoordinator(
            manager, store, management_discovery()
        )
        manager.register_runtime_service(DynamicPluginManager, coordinator)
        coordinator.rescan()

        registration = coordinator.install(
            "dynamic.core",
            "management-tools-plugin-instance",
            scope_id=ScopeId("agent:a"),
        )
        assert registration.descriptor.name == (
            "management-tools-plugin-template@agent-a"
        )
        assert registration.scope_id == ScopeId("agent:a")

        with pytest.raises(RuntimeMutationError, match="one plugin per module"):
            coordinator.install(
                "dynamic.core",
                "management-tools-plugin-template",
                scope_id=ScopeId("agent"),
            )

        enabled = coordinator.set_enabled(
            "management-tools-plugin-template@agent-a",
            True,
            scope_id=ScopeId("agent:a"),
        )
        assert enabled.enabled is True
        assert MANAGEMENT_TOOLS <= set(tool_names(manager, "agent:a"))
        assert MANAGEMENT_TOOLS.isdisjoint(tool_names(manager, "agent"))
    finally:
        manager.stop()


def test_management_tools_reach_an_agent_loop_and_leave_on_disable() -> None:
    manager = make_loop_manager()
    try:
        install_templates(manager)
        materialize_loop(manager)
        store = InMemoryRuntimeStateStore()
        coordinator = RuntimeMutationCoordinator(
            manager, store, management_discovery()
        )
        manager.register_runtime_service(DynamicPluginManager, coordinator)
        coordinator.rescan()

        assert MANAGEMENT_TOOLS.isdisjoint(loop_tool_names(manager))

        coordinator.install(
            "dynamic.core",
            "management-tools-plugin-template",
            scope_id=ScopeId("agent"),
        )
        coordinator.set_enabled(
            "management-tools-plugin-template", True, scope_id=ScopeId("agent")
        )
        assert MANAGEMENT_TOOLS <= set(loop_tool_names(manager))

        coordinator.set_enabled(
            "management-tools-plugin-template", False, scope_id=ScopeId("agent")
        )
        assert MANAGEMENT_TOOLS.isdisjoint(loop_tool_names(manager))
    finally:
        manager.stop()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_dynamic_plugin_e2e.py -k management -v`
Expected: FAIL(收集/断言失败:动态包尚无管理贡献,或 loop 工具集为空)。

- [ ] **Step 3: 修复实现缺口(仅当失败原因在 src)**

本任务纯测试;若失败源于前序任务代码缺陷,先修复对应 src 并重跑 Step 2,不得放宽测试断言。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_dynamic_plugin_e2e.py -v`
Expected: PASS

- [ ] **Step 5: 全量验证**

Run: `make check`
Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add tests/test_dynamic_plugin_e2e.py
git commit -m "test: e2e coverage for management tools visibility and lifecycle"
```

---

### Task 8: README 文档

**Files:**
- Modify: `README.md`(Interactive commands 章节内新增小节)

**Interfaces:**
- Consumes: Task 6 的贡献 id/注册名、Task 5 的 9 个工具名与 confirm token。
- Produces: 无代码接口。

- [ ] **Step 1: 追加文档**

在 README `## Interactive commands` 的 `/scope` 小节之后新增:

````markdown
### 管理工具(给 agent loop 用的 plugin/scope 操作)

`management-tools` 是一个可动态安装的 `agent.plugin.tools` 插件,把
`/plugins`(运行时面)与 `/scope` 的操作包装成 9 个 LangChain 工具,供
agent loop 的 LLM 调用:

| 工具 | 说明 |
| --- | --- |
| `list_scope_tree` | 查看运行时作用域树 |
| `list_runtime_plugins` | 列出已装运行时插件(可按 scope 过滤) |
| `discover_plugins` | 重新扫描并列出可发现包 |
| `install_plugin` | 安装发现的插件贡献(必须显式 scope,初始 disabled) |
| `enable_plugin` / `disable_plugin` | 按 (name, scope) 启停插件 |
| `upgrade_plugin` | 升级到包最新版本 |
| `uninstall_plugin` | 卸载并删除持久化注册 |
| `update_plugin_properties` | 更新运行时属性(runtime set) |

每个工具的 description 写明用途、使用时机与 scope 约束;危险操作带
入参级确认:`disable_plugin` 必须传 `confirm='DISABLE'`,
`uninstall_plugin` 必须传 `confirm='UNINSTALL'`。

开关完全复用现有动态插件机制:

```text
/plugins install dynamic.core management-tools-plugin-template --scope agent
/plugins enable management-tools-plugin-template --scope agent
/plugins disable management-tools-plugin-template --scope agent
```

装到 `agent` 作用域时所有 agent loop 可见;装 `management-tools-plugin-instance`
到 `agent:<id>` 时仅该 agent 可见(注册名带 `@agent-<id>` 后缀,用
`/plugins list` 查准确名字)。两种贡献共用同一模块,**二选一安装**;
LLM 也可以自己 disable 自己的管理工具(需 confirm),重新开启由 CLI/API
完成。重启后按持久化状态自动恢复。
````

- [ ] **Step 2: 全量验证**

Run: `make check`
Expected: 全绿(纯文档变更)。

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document the management tools for agent loops"
```

---

## 完成判定

- [ ] 9 个工具全部带 args_schema(scope 词汇校验 + confirm 强制)与五要素 description
- [ ] `dynamic.core` 可安装/启停管理插件,agent 与 `agent:<id>` 两种可见性经 e2e 验证
- [ ] 同 module 二贡献守卫生效(单元 + e2e 覆盖)
- [ ] CLI/API/工具三处共用 `is_runtime_scope`;CLI/工具共用 `render_scope_tree`
- [ ] `make check` 全绿,覆盖率 ≥95%
- [ ] 每个任务独立 commit,提交历史线性
