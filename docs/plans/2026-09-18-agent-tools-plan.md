# agent 管理工具(ToolExport 动态注册)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 agent 管理操作(list/get/create/update)以 ToolExport 声明式包 `agent.tools` 动态发现、注册进所有 agent loop,带入参约束与提示词,不暴露 delete。

**Architecture:** 新组件 `AgentOperationsExport`(`langharmess_core/plugins/agents/export.py`)实现 `ToolExportTarget.invoke_export` 分发到 `AgentRegistryProvider`;`agent_tools_package()` 声明 4 个 `ToolExport`(name/description/args_schema/destructive),经 `langharmess.plugins` 入口点被发现;install 时 coordinator `_install_adapters` 自动创建适配器落 agent 作用域,loop 重建后工具进入流程。

**Tech Stack:** Python 3.13、Pelix/iPOPO、LangChain(langchain-core ≥1.6.2)、pydantic ≥2.13.5、pytest。

## Global Constraints

- 质量门槛(AGENTS.md):每个 commit 必须过 `make check`(Ruff → mypy → Pyright → clean-process import 检查 → pytest),单元覆盖率 ≥95%。
- TDD:先写失败测试,再写最小实现;每个任务独立 commit。
- 生产代码 mypy strict、Pyright standard 不允许全局放宽;e2e 测试文件头已有 `# mypy: ignore-errors` 属既有豁免,不新增豁免。
- 插件间通信只走 Pelix service spec(Protocol);描述符只在 `langharmess_core/plugin.py` 构建,组件实现在 `plugins/<topic>/<name>.py`。
- 文档(docs/、README)用中文,代码/命令用英文;commit message 风格 `feat:` / `test:` / `docs:`。
- 设计文档:`docs/designs/2026-09-18-agent-tools-design.md`(已提交 c7b98d0)。

---

### Task 1: 导出服务 + schemas + 提示词常量

**Files:**
- Create: `src/langharmess_core/plugins/agents/export.py`
- Test: `tests/test_agent_tools.py`(新建)

**Interfaces:**
- Consumes: `AgentRegistryProvider` 协议(`langharmess_core.contracts`)、`ToolExportTarget` / `SPEC_TOOL_EXPORT_TARGET`(`langharmess_plugin.contracts`)、`ContractGuard`。
- Produces(本文件,Task 2 复用):
  - `AGENT_ID_PATTERN = r"^[A-Za-z0-9._-]{1,64}$"`
  - schemas:`ListAgentsArgs`(空)、`GetAgentArgs`(agent_id)、`CreateAgentArgs`(agent_id/name?/description?)、`UpdateAgentArgs`(agent_id/name?/description?/enabled?/confirm: Literal["DISABLE"]|None,`model_validator` 强制 enabled=False → confirm=="DISABLE")
  - `AGENT_TOOL_EXPORTS: tuple[ToolExport, ...]`(4 个,update_agent `destructive=True`)
  - `AgentOperationsExport`(factory `agent-operations-export-factory`,`@Provides(ToolExportTarget)`,`@RequiresBest("_registry", AgentRegistryProvider, optional=True, immediate_rebind=True)`);`invoke_export` 分发 list/get/create/update,错误统一 `{"error": ...}`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_agent_tools.py`:

```python
"""Unit tests for the agent operations export service and schemas."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from langharmess_core.plugins.agents.export import (
    AGENT_TOOL_EXPORTS,
    AgentOperationsExport,
    CreateAgentArgs,
    GetAgentArgs,
    UpdateAgentArgs,
)


class FakeRegistry:
    def __init__(self) -> None:
        self.agents = [
            {"id": "a1", "name": "A1", "description": "", "enabled": True}
        ]
        self.created: list[tuple[str, str, str]] = []
        self.updated: list[tuple[str, dict[str, Any]]] = []

    def list_agents(self) -> list[dict[str, Any]]:
        return [dict(agent) for agent in self.agents]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        for agent in self.agents:
            if agent["id"] == agent_id:
                return dict(agent)
        return None

    def create_agent(
        self, agent_id: str, name: str, description: str
    ) -> dict[str, Any]:
        self.created.append((agent_id, name, description))
        agent = {
            "id": agent_id,
            "name": name or agent_id,
            "description": description,
            "enabled": True,
        }
        self.agents.append(agent)
        return dict(agent)

    def update_agent(
        self,
        agent_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        self.updated.append(
            (agent_id, {"name": name, "description": description, "enabled": enabled})
        )
        for agent in self.agents:
            if agent["id"] == agent_id:
                if name is not None:
                    agent["name"] = name
                if description is not None:
                    agent["description"] = description
                if enabled is not None:
                    agent["enabled"] = enabled
                return dict(agent)
        raise ValueError(f"Agent not found: {agent_id!r}")


def _service(registry: Any = None) -> AgentOperationsExport:
    service = AgentOperationsExport()
    service._registry = registry
    return service


def test_list_agents_returns_registry_view() -> None:
    result = _service(FakeRegistry()).invoke_export("list_agents", {})
    assert result == {"agents": [{"id": "a1", "name": "A1", "description": "", "enabled": True}]}


def test_get_agent_found_and_missing() -> None:
    service = _service(FakeRegistry())
    assert service.invoke_export("get_agent", {"agent_id": "a1"})["id"] == "a1"
    assert service.invoke_export("get_agent", {"agent_id": "nope"}) == {
        "error": "Agent not found: 'nope'"
    }


def test_create_agent_dispatches_and_defaults_name() -> None:
    registry = FakeRegistry()
    result = _service(registry).invoke_export(
        "create_agent", {"agent_id": "billing", "name": "", "description": "bills"}
    )
    assert registry.created == [("billing", "", "bills")]
    assert result["id"] == "billing"
    assert result["name"] == "billing"


def test_update_agent_passes_only_present_fields() -> None:
    registry = FakeRegistry()
    result = _service(registry).invoke_export(
        "update_agent", {"agent_id": "a1", "description": "new"}
    )
    assert registry.updated == [
        ("a1", {"name": None, "description": "new", "enabled": None})
    ]
    assert result["description"] == "new"


def test_update_agent_value_error_maps_to_error_dict() -> None:
    result = _service(FakeRegistry()).invoke_export(
        "update_agent", {"agent_id": "nope"}
    )
    assert result == {"error": "Agent not found: 'nope'"}


def test_unknown_operation_maps_to_error_dict() -> None:
    result = _service(FakeRegistry()).invoke_export("delete_agent", {"agent_id": "a1"})
    assert result == {"error": "Unknown operation: delete_agent"}


def test_registry_unavailable_maps_to_error_dict() -> None:
    assert _service(None).invoke_export("list_agents", {}) == {
        "error": "Agent registry unavailable"
    }


def test_tool_exports_declare_four_operations() -> None:
    by_name = {export.name: export for export in AGENT_TOOL_EXPORTS}
    assert set(by_name) == {
        "list_agents",
        "get_agent",
        "create_agent",
        "update_agent",
    }
    assert by_name["update_agent"].destructive is True
    assert all(export.target_scope == "agent" for export in AGENT_TOOL_EXPORTS)
    assert by_name["get_agent"].args_schema is GetAgentArgs
    assert by_name["create_agent"].args_schema is CreateAgentArgs


def test_update_agent_schema_requires_confirm_to_disable() -> None:
    with pytest.raises(ValidationError):
        UpdateAgentArgs(agent_id="a1", enabled=False)
    with pytest.raises(ValidationError):
        UpdateAgentArgs(agent_id="a1", enabled=False, confirm="DISABLE-IT")
    model = UpdateAgentArgs(agent_id="a1", enabled=False, confirm="DISABLE")
    assert model.enabled is False


def test_schemas_reject_invalid_agent_ids() -> None:
    with pytest.raises(ValidationError):
        GetAgentArgs(agent_id="bad id")
    with pytest.raises(ValidationError):
        CreateAgentArgs(agent_id="x" * 65)
    assert GetAgentArgs(agent_id="web-1.billing").agent_id == "web-1.billing"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_agent_tools.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'langharmess_core.plugins.agents.export'`

- [ ] **Step 3: 最小实现**

新建 `src/langharmess_core/plugins/agents/export.py`:

```python
"""ToolExport service wrapping agent registry operations."""

from __future__ import annotations

from typing import Any, Literal

from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Property,
    Provides,
    RequiresBest,
    UnbindField,
)
from pydantic import BaseModel, Field, model_validator

from langharmess_core.contracts import AgentRegistryProvider
from langharmess_plugin.contracts import ToolExportTarget
from langharmess_plugin.package import ToolExport
from langharmess_plugin.validation import ContractGuard

AGENT_ID_PATTERN = r"^[A-Za-z0-9._-]{1,64}$"
AGENT_ID_HELP = "Agent id matching ^[A-Za-z0-9._-]{1,64}$."


class ListAgentsArgs(BaseModel):
    """Empty schema for the parameterless listing tool."""


class GetAgentArgs(BaseModel):
    agent_id: str = Field(pattern=AGENT_ID_PATTERN, description=AGENT_ID_HELP)


class CreateAgentArgs(BaseModel):
    agent_id: str = Field(pattern=AGENT_ID_PATTERN, description=AGENT_ID_HELP)
    name: str | None = Field(
        default=None, description="Display name; defaults to agent_id."
    )
    description: str | None = Field(
        default=None, description="What this agent is for."
    )


class UpdateAgentArgs(BaseModel):
    agent_id: str = Field(pattern=AGENT_ID_PATTERN, description=AGENT_ID_HELP)
    name: str | None = Field(default=None, description="New display name; omit to keep.")
    description: str | None = Field(default=None, description="New description; omit to keep.")
    enabled: bool | None = Field(default=None, description="Set false to disable; omit to keep.")
    confirm: Literal["DISABLE"] | None = Field(
        default=None,
        description="Required, exactly 'DISABLE', when enabled=false.",
    )

    @model_validator(mode="after")
    def _confirm_required_for_disable(self) -> UpdateAgentArgs:
        if self.enabled is False and self.confirm != "DISABLE":
            raise ValueError("Disabling an agent requires confirm='DISABLE'")
        return self


_LIST_AGENTS_DESCRIPTION = (
    "List every registered agent with its id, name, description, and "
    "enabled state. Use it before get/create/update to learn exact "
    "agent ids. Returns {\"agents\": [...]}, or {\"error\": ...}."
)

_GET_AGENT_DESCRIPTION = (
    "Fetch one agent by id (pattern ^[A-Za-z0-9._-]{1,64}$). Use it to "
    "check an agent's current state before updating it. Returns the "
    "agent dict, or {\"error\": ...}."
)

_CREATE_AGENT_DESCRIPTION = (
    "Create a new agent and bring it online — its plugin set and loop "
    "are materialized automatically. Check list_agents first so the id "
    "does not already exist. name defaults to the id. Returns the "
    "created agent dict, or {\"error\": ...}."
)

_UPDATE_AGENT_DESCRIPTION = (
    "Update an agent's name, description, or enabled state. Only pass "
    "the fields you want to change. Disabling removes the agent's loop "
    "until re-enabled; it is semi-destructive, so enabled=false "
    "requires confirm='DISABLE' exactly. Example: "
    "update_agent(agent_id='billing', description='Handles invoices', "
    "enabled=False, confirm='DISABLE'). Returns the updated agent "
    "dict, or {\"error\": ...}."
)


AGENT_TOOL_EXPORTS: tuple[ToolExport, ...] = (
    ToolExport("list_agents", _LIST_AGENTS_DESCRIPTION, "list_agents", ListAgentsArgs),
    ToolExport("get_agent", _GET_AGENT_DESCRIPTION, "get_agent", GetAgentArgs),
    ToolExport("create_agent", _CREATE_AGENT_DESCRIPTION, "create_agent", CreateAgentArgs),
    ToolExport(
        "update_agent",
        _UPDATE_AGENT_DESCRIPTION,
        "update_agent",
        UpdateAgentArgs,
        destructive=True,
    ),
)


@ComponentFactory("agent-operations-export-factory")
@Provides(ToolExportTarget)
@Property("_plugin_name", "plugin.name", "agent-operations-export")
@Property("_plugin_version", "plugin.version", "1.0.0")
@RequiresBest(
    "_registry", AgentRegistryProvider, optional=True, immediate_rebind=True
)
class AgentOperationsExport:
    """Dispatches tool-export operations to the agent registry service."""

    def __init__(self) -> None:
        self._plugin_name = "agent-operations-export"
        self._plugin_version = "1.0.0"
        self._registry: Any = None
        self._guard = ContractGuard(self, "_registry", AgentRegistryProvider)

    @BindField("_registry", if_valid=True)
    def _on_registry_bind(self, field: str, service: Any, reference: Any) -> None:
        if not self._guard.admit(service):
            return

    @UnbindField("_registry")
    def _on_registry_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._guard.release(service)

    def invoke_export(self, operation: str, arguments: dict[str, Any]) -> Any:
        registry = self._registry
        if registry is None:
            return {"error": "Agent registry unavailable"}
        try:
            if operation == "list_agents":
                return {"agents": registry.list_agents()}
            if operation == "get_agent":
                agent = registry.get_agent(str(arguments["agent_id"]))
                if agent is None:
                    return {"error": f"Agent not found: {arguments['agent_id']!r}"}
                return agent
            if operation == "create_agent":
                return registry.create_agent(
                    str(arguments["agent_id"]),
                    str(arguments.get("name") or ""),
                    str(arguments.get("description") or ""),
                )
            if operation == "update_agent":
                fields = {
                    key: arguments[key]
                    for key in ("name", "description", "enabled")
                    if key in arguments and arguments[key] is not None
                }
                return registry.update_agent(str(arguments["agent_id"]), **fields)
            return {"error": f"Unknown operation: {operation}"}
        except ValueError as exc:
            return {"error": str(exc)}

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_agent_tools.py -q`
Expected: PASS

- [ ] **Step 5: 全量验证**

Run: `make check`
Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add src/langharmess_core/plugins/agents/export.py tests/test_agent_tools.py
git commit -m "feat: add agent operations export service with tool schemas"
```

---

### Task 2: 包声明 + 入口点

**Files:**
- Modify: `src/langharmess_core/plugin.py`(`agent_tools_package`)
- Modify: `pyproject.toml`(entry point `agent-tools`)
- Test: `tests/test_packaging.py`(追加断言)、`tests/test_agent_tools.py`(追加包结构断言)

**Interfaces:**
- Consumes: Task 1 的 `AGENT_TOOL_EXPORTS`;`SPEC_TOOL_EXPORT_TARGET`(`langharmess_plugin.contracts`,plugin.py 需新增该 import)。
- Produces: `agent_tools_package() -> PluginPackage`(id `agent.tools`,贡献 id `agent-operations`,descriptor 名 `agent-operations-export`,target `agent`,enabled=True,scope `agent`);入口点 `agent-tools = "langharmess_core.plugin:agent_tools_package"`。Task 3 e2e 与 Task 4 README 依赖这些名字。

- [ ] **Step 1: 写失败测试**

`tests/test_packaging.py` 的 `test_console_script_and_packaging_dependencies_are_declared` 中 `assert plugins["dynamic-core"] == ...` 之后追加:

```python
    assert plugins["agent-tools"] == "langharmess_core.plugin:agent_tools_package"
```

`tests/test_agent_tools.py` 末尾追加(文件头补
`from langharmess_core.plugin import agent_tools_package`
与 `from langharmess_plugin.contracts import SPEC_TOOL_EXPORT_TARGET`):

```python
def test_agent_tools_package_declares_discoverable_contribution() -> None:
    package = agent_tools_package()
    assert package.id == "agent.tools"
    assert package.version == "1.0.0"
    assert [item.id for item in package.contributions] == ["agent-operations"]
    contribution = package.contributions[0]
    assert contribution.target == "agent"
    assert contribution.tool_exports == AGENT_TOOL_EXPORTS
    descriptor = contribution.descriptor
    assert descriptor.name == "agent-operations-export"
    assert descriptor.instance == "agent-operations-export"
    assert descriptor.module == "langharmess_core.plugins.agents.export"
    assert descriptor.factory == "agent-operations-export-factory"
    assert descriptor.specification == SPEC_TOOL_EXPORT_TARGET
    assert descriptor.enabled is True
    assert descriptor.scope == "agent"
    assert descriptor.scope_parent == "root"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_packaging.py tests/test_agent_tools.py -q`
Expected: FAIL——pyproject 断言失败(KeyError 'agent-tools')、`agent_tools_package` 未定义。

- [ ] **Step 3: 最小实现**

`src/langharmess_core/plugin.py`:

1. 导入区追加(在 `langharmess_plugin.package` 导入行附近):

```python
from langharmess_plugin.contracts import SPEC_TOOL_EXPORT_TARGET
```

   并在文件顶部(模块导入后)加:

```python
from langharmess_core.plugins.agents.export import AGENT_TOOL_EXPORTS
```

2. 文件末尾追加:

```python
def agent_tools_package() -> PluginPackage:
    """Describe the agent management tools installed via dynamic discovery."""
    return PluginPackage(
        id="agent.tools",
        version="1.0.0",
        contributions=(
            PluginContribution(
                "agent-operations",
                "agent",
                PluginDescriptor(
                    name="agent-operations-export",
                    version="1.0.0",
                    module="langharmess_core.plugins.agents.export",
                    factory="agent-operations-export-factory",
                    instance="agent-operations-export",
                    specification=SPEC_TOOL_EXPORT_TARGET,
                    scope="agent",
                    scope_parent="root",
                    enabled=True,
                ),
                tool_exports=AGENT_TOOL_EXPORTS,
            ),
        ),
    )
```

`pyproject.toml` 的 `[project.entry-points."langharmess.plugins"]` 表内(按字母序,`builtin-*` 之前)加一行:

```toml
agent-tools = "langharmess_core.plugin:agent_tools_package"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_packaging.py tests/test_agent_tools.py tests/test_plugin_discovery.py -q`
Expected: PASS

- [ ] **Step 5: 全量验证**

Run: `make check`
Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add src/langharmess_core/plugin.py pyproject.toml tests/test_packaging.py tests/test_agent_tools.py
git commit -m "feat: declare the agent-tools package for dynamic discovery"
```

---

### Task 3: e2e——发现/安装/启停/loop 视角 + 真实 registry 创建

**Files:**
- Test: `tests/test_dynamic_plugin_e2e.py`(追加 3 个用例)

**Interfaces:**
- Consumes: Task 2 的包/贡献/描述符名;既有 e2e helper(`make_manager`/`make_loop_manager`/`materialize_loop`/`install_templates`/`tool_names`/`loop_tool_names`/`EntryPoint`/`management_discovery` 模式);`agent_registry_descriptor`(plugin.py 既有)。
- Produces: 无对外接口,仅测试。

- [ ] **Step 1: 写失败测试**

`tests/test_dynamic_plugin_e2e.py`:

1. 头部 `from langharmess_core.contracts import SPEC_AGENT_LOOP, SPEC_LLM, SPEC_TOOL` 改为:

```python
from langharmess_core.contracts import (
    SPEC_AGENT_LOOP,
    SPEC_AGENT_REGISTRY,
    SPEC_LLM,
    SPEC_TOOL,
)
```

   并在 `from langharmess_core.plugin import (...)` 的导入元组追加
   `agent_registry_descriptor`、`agent_tools_package`;文件头补
   `from pathlib import Path`。

2. `MANAGEMENT_TOOLS` 常量之后追加:

```python
AGENT_TOOLS = {"list_agents", "get_agent", "create_agent", "update_agent"}
```

3. 文件末尾追加 3 个测试:

```python
def test_agent_tools_install_enable_disable_visibility() -> None:
    manager = make_manager()
    try:
        install_templates(manager)
        store = InMemoryRuntimeStateStore()
        discovery = PluginDiscovery(
            lambda: [EntryPoint(agent_tools_package(), "agent-tools")]
        )
        coordinator = RuntimeMutationCoordinator(manager, store, discovery)
        coordinator.rescan()

        registration = coordinator.install(
            "agent.tools", "agent-operations", scope_id=ScopeId("agent")
        )
        assert registration.descriptor.name == "agent-operations-export"
        assert AGENT_TOOLS <= set(tool_names(manager, "agent"))
        assert AGENT_TOOLS.isdisjoint(tool_names(manager, "ui"))

        disabled = coordinator.set_enabled(
            "agent-operations-export", False, scope_id=ScopeId("agent")
        )
        assert disabled.enabled is False
        assert AGENT_TOOLS.isdisjoint(tool_names(manager, "agent"))

        enabled = coordinator.set_enabled(
            "agent-operations-export", True, scope_id=ScopeId("agent")
        )
        assert enabled.enabled is True
        assert AGENT_TOOLS <= set(tool_names(manager, "agent"))
    finally:
        manager.stop()


def test_agent_tools_reach_an_agent_loop() -> None:
    manager = make_loop_manager()
    try:
        install_templates(manager)
        materialize_loop(manager)
        store = InMemoryRuntimeStateStore()
        discovery = PluginDiscovery(
            lambda: [EntryPoint(agent_tools_package(), "agent-tools")]
        )
        coordinator = RuntimeMutationCoordinator(manager, store, discovery)
        coordinator.rescan()

        assert AGENT_TOOLS.isdisjoint(loop_tool_names(manager))

        coordinator.install(
            "agent.tools", "agent-operations", scope_id=ScopeId("agent")
        )
        assert AGENT_TOOLS <= set(loop_tool_names(manager))
    finally:
        manager.stop()


def test_agent_tools_create_agent_through_real_registry(tmp_path: Path) -> None:
    manager = make_loop_manager()
    try:
        install_templates(manager)
        manager.install_plugin(agent_registry_descriptor(str(tmp_path)))
        store = InMemoryRuntimeStateStore()
        discovery = PluginDiscovery(
            lambda: [EntryPoint(agent_tools_package(), "agent-tools")]
        )
        coordinator = RuntimeMutationCoordinator(manager, store, discovery)
        coordinator.rescan()
        coordinator.install(
            "agent.tools", "agent-operations", scope_id=ScopeId("agent")
        )

        providers = manager.find_services(
            SPEC_TOOL, manager.scope_filter(ScopeId("agent"))
        )
        create_tool = next(
            tool
            for provider in providers
            for tool in provider.get_tools()
            if tool.name == "create_agent"
        )
        result = create_tool.invoke(
            {
                "agent_id": "billing",
                "name": "Billing",
                "description": "Handles invoices",
            }
        )
        assert result["id"] == "billing"

        registry = manager.find_service(SPEC_AGENT_REGISTRY)
        assert registry is not None
        assert [item["id"] for item in registry.list_agents()] == [
            "simple_agent",
            "billing",
        ]
    finally:
        manager.stop()
```

(registry 插件对全新 agents.json 会播种默认 `simple_agent`,故断言包含它。)

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_dynamic_plugin_e2e.py -q -k agent_tools`
Expected: FAIL(收集错误:`agent_tools_package` 未导出、`Path` 未导入等;若收集通过则断言失败)。

- [ ] **Step 3: 修复实现缺口(仅当失败原因在 src)**

本任务纯测试;若失败源于前序任务代码缺陷,先修复对应 src 并重跑 Step 2,不得放宽测试断言。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_dynamic_plugin_e2e.py -q`
Expected: PASS

- [ ] **Step 5: 全量验证**

Run: `make check`
Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add tests/test_dynamic_plugin_e2e.py
git commit -m "test: e2e coverage for agent tools discovery and registry wiring"
```

---

### Task 4: README 文档

**Files:**
- Modify: `README.md`(管理工具小节之后新增)

**Interfaces:**
- Consumes: Task 2 的包/贡献/工具名、confirm token。
- Produces: 无代码接口。

- [ ] **Step 1: 追加文档**

在 README 管理工具小节(「重启后按持久化状态自动恢复。」段落)之后新增:

````markdown
### agent 管理工具(agent-tools 包)

`agent.tools` 是一个声明式包,把 agent 管理操作以 `ToolExport` 动态
发现、注册成 LangChain 工具,供所有 agent loop 的 LLM 调用:

| 工具 | 说明 |
| --- | --- |
| `list_agents` | 列出全部 agent 及 enabled 状态 |
| `get_agent` | 按 agent_id 查单个 agent |
| `create_agent` | 创建新 agent(自动物化 loop) |
| `update_agent` | 改名/改描述/启停;`enabled=false` 必须传 `confirm='DISABLE'` |

`delete_agent` 不暴露,删除只能由 operator 经 API/CLI 执行。安装方式
与动态插件一致:

```text
/plugins install agent.tools agent-operations --scope agent
/plugins enable agent-operations-export --scope agent
```

安装后适配器自动落 agent 作用域,所有 agent loop 重建即获得这 4 个
工具;`/plugins disable` 立即移除。
````

- [ ] **Step 2: 全量验证**

Run: `make check`
Expected: 全绿(纯文档变更)。

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document the agent management tools package"
```

---

## 完成判定

- [ ] `agent.tools` 经入口点被 discovery 发现,e2e 覆盖 install/enable/disable 可见性
- [ ] 4 个工具进入所有 agent loop(loop 视角 e2e);`create_agent` 经真实 registry 服务验证
- [ ] 入参约束(agent_id pattern、enabled=false 强制 confirm)单元覆盖
- [ ] `update_agent` 标记 destructive;delete 不暴露
- [ ] `make check` 全绿,覆盖率 ≥95%
- [ ] 每个任务独立 commit,提交历史线性
