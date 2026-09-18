# Scope 固定拓扑、常量集中与 /scope 接口 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 固定 scope 拓扑为 root→server/agent/ui、agent→agent:{id}(冒号格式),常量集中到 `langharness_plugin/scope_const.py`,并新增 API `GET /scope` 与 CLI `/scope` 命令。

**Architecture:** `scope_const.py` 成为所有固定 SCOPE_ID 与元数据 key 的唯一权威来源;`PluginManager.start()` 全局种入固定拓扑;coordinator 恢复逻辑改为"已存在则跳过 + 过滤旧格式"实现旧数据自愈;API 新增 scopes 路由插件(绑定 `DynamicPluginManager`),CLI 新增 scope 命令插件(HTTP 客户端渲染缩进树)。

**Tech Stack:** Python 3.13、Pelix/iPOPO 组件模型、FastAPI(路由)、httpx(CLI 客户端)、pytest + pytest-cov(95% 门槛)。

**Spec:** `docs/designs/2026-09-17-scope-topology-and-cli-design.md`(commit 6884d1b)

**⚠ 重要环境事实:**
- 本仓库 pre-commit 钩子每次 commit 会依次跑 ruff、mypy、pyright、`pytest tests/test_imports.py`(约 4.5 分钟)和全量 pytest + coverage(约 6.5 分钟,`--cov-fail-under=95`)。**每个任务必须全部绿了再 commit,且新增代码必须被测试覆盖,否则钩子会失败。** 不要用 `--no-verify` 跳过。
- 工作区有用户未提交的改动(`src/langharness_core/plugin.py` 等 6 个文件);所有编辑基于当前工作区内容,不要 revert。
- Pelix 模块重载限制:涉及 bootstrap 的测试按模式拆分,不要在同一次 `_run` 里做跨模式的 monkeypatch(见既有测试习惯)。

---

## 文件结构

| 文件 | 责任 |
|---|---|
| `src/langharness_plugin/scope_const.py`(新) | 固定 SCOPE_ID、元数据 key、`BUILTIN_SCOPES` 拓扑声明、`agent_instance_scope_id` |
| `src/langharness_plugin/plugin_manager.py` | 导入常量;`start()` 末尾调用 `_seed_builtin_scopes()` |
| `src/langharness_plugin/scope_policy.py` | 改从 scope_const 导入 `PLUGIN_SCOPE_ID`/`PLUGIN_KEY` |
| `src/langharness_plugin/contracts.py` | `DynamicPluginManager` 协议新增 `scopes()` |
| `src/langharness_plugin/coordinator.py` | 冒号格式、适配器 `scope_parent`、恢复迁移、`scopes()` 实现 |
| `src/langharness_core/scopes.py` | **删除**,消费方改导入 |
| `src/langharness_core/plugin.py`、`src/langharness_core/plugins/agents/directory.py` | 改导入;agent 模板 `scope_parent` server→root |
| `src/langharness_api/plugins/routes/scopes.py`(新) | `GET /scope` 路由插件 |
| `src/langharness_api/plugin.py` | 注册 `api-scopes` 描述符与贡献项 |
| `src/langharness_cli/plugins/commands/scope.py`(新) | `/scope` 交互命令 + argparse 版 |
| `src/langharness_cli/plugin.py` | 注册 `cli-scope` 描述符与贡献项 |

---

### Task 1: 新建 scope_const.py(固定 SCOPE_ID 唯一权威来源)

**Files:**
- Create: `src/langharness_plugin/scope_const.py`
- Test: `tests/test_scope_const.py`(新)

- [ ] **Step 1: 写失败测试**

创建 `tests/test_scope_const.py`:

```python
"""Canonical scope constants live in one module."""

from __future__ import annotations

from langharness_plugin.scope_const import (
    AGENT_SCOPE_ID,
    BUILTIN_SCOPES,
    PLUGIN_KEY,
    PLUGIN_SCOPE_CHAIN,
    PLUGIN_SCOPE_ID,
    ROOT_SCOPE_ID,
    SERVER_SCOPE_ID,
    UI_SCOPE_ID,
    agent_instance_scope_id,
)
from langharness_scope import ScopeId


def test_builtin_scope_ids_are_canonical() -> None:
    assert UI_SCOPE_ID == ScopeId("ui")
    assert SERVER_SCOPE_ID == ScopeId("server")
    assert AGENT_SCOPE_ID == ScopeId("agent")
    assert ROOT_SCOPE_ID == ScopeId("root")


def test_agent_instance_scope_id_uses_colon_format() -> None:
    assert agent_instance_scope_id("a") == ScopeId("agent:a")


def test_builtin_scopes_declare_the_fixed_topology() -> None:
    assert BUILTIN_SCOPES == (
        (UI_SCOPE_ID, "UI", ROOT_SCOPE_ID),
        (SERVER_SCOPE_ID, "Server", ROOT_SCOPE_ID),
        (AGENT_SCOPE_ID, "Agent", ROOT_SCOPE_ID),
    )


def test_plugin_metadata_keys_are_exported() -> None:
    assert PLUGIN_SCOPE_ID == "plugin.scope_id"
    assert PLUGIN_SCOPE_CHAIN == "plugin.scope_chain"
    assert PLUGIN_KEY == "plugin.key"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_scope_const.py -q`
Expected: FAIL,`ModuleNotFoundError: No module named 'langharness_plugin.scope_const'`

- [ ] **Step 3: 实现模块**

创建 `src/langharness_plugin/scope_const.py`:

```python
"""Canonical scope identifiers and scope-related plugin metadata keys."""

from __future__ import annotations

from langharness_scope import ROOT_SCOPE_ID, ScopeId

UI_SCOPE_ID = ScopeId("ui")
SERVER_SCOPE_ID = ScopeId("server")
AGENT_SCOPE_ID = ScopeId("agent")

PLUGIN_SCOPE_ID = "plugin.scope_id"
PLUGIN_SCOPE_CHAIN = "plugin.scope_chain"
PLUGIN_KEY = "plugin.key"

# The fixed runtime topology: every process seeds these on PluginManager start.
BUILTIN_SCOPES: tuple[tuple[ScopeId, str, ScopeId], ...] = (
    (UI_SCOPE_ID, "UI", ROOT_SCOPE_ID),
    (SERVER_SCOPE_ID, "Server", ROOT_SCOPE_ID),
    (AGENT_SCOPE_ID, "Agent", ROOT_SCOPE_ID),
)


def agent_instance_scope_id(agent_id: str) -> ScopeId:
    return ScopeId(f"agent:{agent_id}")


__all__ = [
    "AGENT_SCOPE_ID",
    "BUILTIN_SCOPES",
    "PLUGIN_KEY",
    "PLUGIN_SCOPE_CHAIN",
    "PLUGIN_SCOPE_ID",
    "ROOT_SCOPE_ID",
    "SERVER_SCOPE_ID",
    "UI_SCOPE_ID",
    "agent_instance_scope_id",
]
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_scope_const.py -q`
Expected: PASS(4 passed)

- [ ] **Step 5: Commit**(钩子约 11 分钟,耐心等待)

```bash
git add src/langharness_plugin/scope_const.py tests/test_scope_const.py
git commit -m "feat: centralize fixed scope ids and plugin metadata keys in scope_const"
```

---

### Task 2: scope_policy 与 plugin_manager 改从 scope_const 导入元数据 key

**Files:**
- Modify: `src/langharness_plugin/scope_policy.py:1-12`
- Modify: `src/langharness_plugin/plugin_manager.py:1-35`

- [ ] **Step 1: 修改 scope_policy.py 导入与常量**

`src/langharness_plugin/scope_policy.py` 当前(第 1-12 行):

```python
"""Plugin-specific visibility and shadowing rules over a generic scope tree."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langharness_scope import ScopeId, ScopeTreeProvider

PLUGIN_SCOPE_ID = "plugin.scope_id"
PLUGIN_KEY = "plugin.key"
```

改为:

```python
"""Plugin-specific visibility and shadowing rules over a generic scope tree."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langharness_plugin.scope_const import PLUGIN_KEY, PLUGIN_SCOPE_ID
from langharness_scope import ScopeId, ScopeTreeProvider
```

- [ ] **Step 2: 修改 plugin_manager.py 导入与常量**

`src/langharness_plugin/plugin_manager.py` 第 22-31 行当前:

```python
from langharness_plugin.scope_policy import PluginScopePolicy
from langharness_plugin.validation import (
    ContractViolationError,
    contract_for,
    validate,
)
from langharness_scope import ROOT_SCOPE_ID, ScopeId, ScopeTree

FILTERS_PROPERTY = "requires.filters"
SERVICE_RANKING = "service.ranking"
SCOPE_RANKING_STRIDE = 1_000_000
PLUGIN_SCOPE_ID = "plugin.scope_id"
PLUGIN_SCOPE_CHAIN = "plugin.scope_chain"
PLUGIN_KEY = "plugin.key"
PLUGIN_RANKING = "plugin.ranking"
```

改为:

```python
from langharness_plugin.scope_const import (
    PLUGIN_KEY,
    PLUGIN_SCOPE_CHAIN,
    PLUGIN_SCOPE_ID,
)
from langharness_plugin.scope_policy import PluginScopePolicy
from langharness_plugin.validation import (
    ContractViolationError,
    contract_for,
    validate,
)
from langharness_scope import ROOT_SCOPE_ID, ScopeId, ScopeTree

FILTERS_PROPERTY = "requires.filters"
SERVICE_RANKING = "service.ranking"
SCOPE_RANKING_STRIDE = 1_000_000
PLUGIN_RANKING = "plugin.ranking"
```

- [ ] **Step 3: 运行回归验证**

Run: `.venv/bin/python -m pytest tests/test_plugin_scope_policy.py tests/test_plugin_manager_unit.py tests/test_plugin_manager_scoped.py tests/test_plugin_scope_service.py -q`
Expected: PASS(行为不变,纯导入迁移)

- [ ] **Step 4: Commit**

```bash
git add src/langharness_plugin/scope_policy.py src/langharness_plugin/plugin_manager.py
git commit -m "refactor: import plugin metadata keys from scope_const"
```

---

### Task 3: PluginManager 全局种子(所有进程启动即种入固定拓扑)

**Files:**
- Modify: `src/langharness_plugin/plugin_manager.py`(start() 与方法区)
- Test: `tests/test_plugin_scope_seed.py`(新)
- Modify: `tests/test_dynamic_plugin_e2e.py:117-124`(移除冗余 ensure)
- Modify: `tests/test_scope_plugin_e2e.py:146,262-265`(移除冗余/冲突 ensure)

- [ ] **Step 1: 写失败测试**

创建 `tests/test_plugin_scope_seed.py`:

```python
"""PluginManager seeds the fixed scope topology on start."""

from __future__ import annotations

import pytest

from langharness_plugin.plugin_manager import PluginManager
from langharness_plugin.registry import PluginRegistry
from langharness_plugin.scope_const import (
    AGENT_SCOPE_ID,
    ROOT_SCOPE_ID,
    SERVER_SCOPE_ID,
    UI_SCOPE_ID,
)
from langharness_scope import ScopeId, ScopeTree


def test_start_seeds_builtin_scopes() -> None:
    manager = PluginManager(PluginRegistry([]))
    manager.start()
    try:
        tree = manager.scope_tree
        assert {scope.id for scope in tree.snapshot().scopes} == {
            ROOT_SCOPE_ID,
            UI_SCOPE_ID,
            SERVER_SCOPE_ID,
            AGENT_SCOPE_ID,
        }
        assert tree.get(AGENT_SCOPE_ID).parent_id == ROOT_SCOPE_ID
        assert tree.get(SERVER_SCOPE_ID).parent_id == ROOT_SCOPE_ID
        assert tree.get(UI_SCOPE_ID).parent_id == ROOT_SCOPE_ID
    finally:
        manager.stop()


def test_seeding_is_idempotent_across_restarts() -> None:
    manager = PluginManager(PluginRegistry([]))
    manager.start()
    manager.stop()
    manager.start()
    try:
        assert len(manager.scope_tree.snapshot().scopes) == 4
    finally:
        manager.stop()


def test_seeding_rejects_a_scope_with_a_conflicting_parent() -> None:
    tree = ScopeTree()
    custom = tree.create(ScopeId("custom"), "Custom")
    tree.create(AGENT_SCOPE_ID, "Agent", custom.id)
    manager = PluginManager(PluginRegistry([]), scope_tree=tree)
    with pytest.raises(ValueError, match="already has a different parent"):
        manager.start()
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_plugin_scope_seed.py -q`
Expected: FAIL(第一个测试:启动后树里只有 root)

- [ ] **Step 3: 实现种子逻辑**

`src/langharness_plugin/plugin_manager.py`:

(a) 导入处(第 22-31 行,Task 2 之后的样子)在 `PLUGIN_SCOPE_CHAIN,` 后加 `BUILTIN_SCOPES,`:

```python
from langharness_plugin.scope_const import (
    BUILTIN_SCOPES,
    PLUGIN_KEY,
    PLUGIN_SCOPE_CHAIN,
    PLUGIN_SCOPE_ID,
)
```

(b) `start()` 末尾(第 84-90 行,`self._scope_registration = ...` 之后)加一行:

```python
        self._scope_registration = self._context.register_service(
            ScopedPluginRegistrar, self, {}
        )
        self._seed_builtin_scopes()
```

(c) 在 `stop()` 之前新增私有方法:

```python
    def _seed_builtin_scopes(self) -> None:
        """Create the fixed runtime topology so every process has the tree."""
        for scope_id, name, parent_id in BUILTIN_SCOPES:
            self.ensure_scope(scope_id, name=name, parent_id=parent_id)
```

- [ ] **Step 4: 修复被种子行为打破的既有测试**

`tests/test_dynamic_plugin_e2e.py` 第 117-124 行当前:

```python
def install_templates(manager: PluginManager) -> None:
    for descriptor in manager.registry.list():
        manager.install_plugin(descriptor)
    manager.ensure_scope(ScopeId("ui"), name="UI")
    manager.ensure_scope(ScopeId("server"), name="Server")
    manager.ensure_scope(ScopeId("agent"), name="Agent", parent_id=ScopeId("server"))
    manager.ensure_scope(ScopeId("agent/a"), name="A", parent_id=ScopeId("agent"))
```

改为(ui/server/agent 已由 start() 种入,只保留 agent 实例 scope):

```python
def install_templates(manager: PluginManager) -> None:
    for descriptor in manager.registry.list():
        manager.install_plugin(descriptor)
    manager.ensure_scope(ScopeId("agent/a"), name="A", parent_id=ScopeId("agent"))
```

`tests/test_scope_plugin_e2e.py` 第 145-148 行删除 `ensure_scope(agent)` 行:

```python
        for descriptor in registry.list():
            manager.install_plugin(descriptor)
        manager.ensure_scope(ScopeId("agent"), name="Agent")
        manager.ensure_scope(
            ScopeId("session"), name="Session", parent_id=ScopeId("agent")
        )
```

改为:

```python
        for descriptor in registry.list():
            manager.install_plugin(descriptor)
        manager.ensure_scope(
            ScopeId("session"), name="Session", parent_id=ScopeId("agent")
        )
```

同文件第 262-265 行当前:

```python
        manager.ensure_scope(ScopeId("ui"), name="UI")
        manager.ensure_scope(ScopeId("server"), name="Server")
        manager.ensure_scope(
            ScopeId("agent"), name="Agent", parent_id=ScopeId("server")
        )
```

整段删除(agent 实例 scope 的 ensure 保留,见下方第 266-272 行)。

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_plugin_scope_seed.py tests/test_dynamic_plugin_e2e.py tests/test_scope_plugin_e2e.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/langharness_plugin/plugin_manager.py tests/test_plugin_scope_seed.py tests/test_dynamic_plugin_e2e.py tests/test_scope_plugin_e2e.py
git commit -m "feat: seed the fixed scope topology on PluginManager start"
```

---

### Task 4: agent 实例 scope 冒号格式迁移(agent/a → agent:a)

**Files:**
- Modify: `src/langharness_plugin/coordinator.py:244-260,316,330`
- Modify: `src/langharness_core/plugin.py:31`、`src/langharness_core/plugins/agents/directory.py:33`(改导入)
- Delete: `src/langharness_core/scopes.py`
- Modify: `tests/test_imports.py:27,32-33`
- Modify: `tests/test_runtime_mutation_coordinator.py:279,284,292,535`
- Modify: `tests/test_dynamic_plugin_e2e.py:124,146,155,163,185,187`
- Modify: `tests/test_scope_plugin_e2e.py:268,271,278-279,304,310-311`
- Modify: `tests/test_agent_directory.py:190-193,294`
- Modify: `tests/test_plugin_scope_classification.py:82`

- [ ] **Step 1: 改 coordinator 格式判断**

`src/langharness_plugin/coordinator.py` 第 251-253 行当前:

```python
        if scope_id is None or not str(scope_id).startswith("agent/"):
            raise RuntimeMutationError("agent_instance contribution requires agent/<id>")
        suffix = str(scope_id).replace("/", "-")
```

改为:

```python
        if scope_id is None or not str(scope_id).startswith("agent:"):
            raise RuntimeMutationError("agent_instance contribution requires agent:<id>")
        suffix = str(scope_id).replace(":", "-")
```

第 330 行当前:

```python
                scope_parent="agent" if target_scope.startswith("agent/") else "server",
```

改为:

```python
                scope_parent="agent" if target_scope.startswith("agent:") else "server",
```

(`scope_parent="server"` 在 Task 5 再改成 root。)

- [ ] **Step 2: 切换消费方导入并删除 core/scopes.py**

`src/langharness_core/plugin.py` 第 31 行:

```python
from langharness_core.scopes import agent_instance_scope_id
```

改为:

```python
from langharness_plugin.scope_const import agent_instance_scope_id
```

`src/langharness_core/plugins/agents/directory.py` 第 33 行:

```python
from langharness_core.scopes import AGENT_SCOPE_ID, agent_instance_scope_id
```

改为:

```python
from langharness_plugin.scope_const import AGENT_SCOPE_ID, agent_instance_scope_id
```

删除文件:

```bash
git rm src/langharness_core/scopes.py
```

- [ ] **Step 3: 更新 test_imports.py 模块清单**

`tests/test_imports.py` 删除第 27 行 `"langharness_core.scopes",`;在 `"langharness_plugin.scope_policy",` 之前插入 `"langharness_plugin.scope_const",`。

- [ ] **Step 4: 更新受影响测试的格式断言(逐个替换,共 6 个文件)**

`tests/test_runtime_mutation_coordinator.py`:

- 第 279 行:`scope_id=ScopeId("agent/a")` → `scope_id=ScopeId("agent:a")`
- 第 284 行:`assert registration.scope_id == ScopeId("agent/a")` → `ScopeId("agent:a")`
- 第 292 行:`with pytest.raises(RuntimeError, match="agent/<id>"):` → `match="agent:<id>"`
- 第 535 行:`{"id": "agent/a", "parent_id": "agent", "name": "A"},` → `"agent:a"`
  (注意:第 282-283 行的 `"instance@agent-a"` 断言不变 —— 冒号与斜杠的 suffix 替换结果相同)

`tests/test_dynamic_plugin_e2e.py`(6 处,全部 `"agent/a"` → `"agent:a"`):

- 第 124 行:`manager.ensure_scope(ScopeId("agent/a"), name="A", parent_id=ScopeId("agent"))` → `ScopeId("agent:a")`
- 第 146 行:`"example.agent-echo", "echo", scope_id=ScopeId("agent/a")` → `ScopeId("agent:a")`
- 第 155 行:集合字面量 `"agent/a",` → `"agent:a",`
- 第 163 行:列表字面量 `"agent/a",` → `"agent:a",`
- 第 185 行:`ScopeId("agent/a"),` → `ScopeId("agent:a"),`
- 第 187 行:`("ui", "server", "agent", "agent/a")` → `("ui", "server", "agent", "agent:a")`

`tests/test_scope_plugin_e2e.py`:

- 第 268 行:`ScopeId("agent/a"), name="A", parent_id=ScopeId("agent")` → `ScopeId("agent:a")`
- 第 271 行:`ScopeId("agent/b"), name="B", parent_id=ScopeId("agent")` → `ScopeId("agent:b")`
- 第 278-279 行:`("agent/a", agent_a_tool),` → `("agent:a", agent_a_tool),`;`("agent/b", agent_b_tool),` → `("agent:b", agent_b_tool),`
- 第 304 行:`assert visible("agent/a") == {` → `assert visible("agent:a") == {`
- 第 310-311 行:`not in visible("agent/a")` → `not in visible("agent:a")`(两处)

`tests/test_agent_directory.py`:

- 第 190-193 行:4 行 LDAP 过滤器字符串中的 `plugin.scope_id=agent/simple_agent` → `plugin.scope_id=agent:simple_agent`(仅替换 `agent/simple_agent`,其余不动 —— server 子句在 Task 5 移除)
- 第 294 行:`ScopeId("agent/simple_agent")` → `ScopeId("agent:simple_agent")`

`tests/test_plugin_scope_classification.py` 第 82 行:

```python
        ("agent/alpha", "agent")
```

改为:

```python
        ("agent:alpha", "agent")
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_runtime_mutation_coordinator.py tests/test_dynamic_plugin_e2e.py tests/test_scope_plugin_e2e.py tests/test_agent_directory.py tests/test_plugin_scope_classification.py tests/test_scope_const.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/langharness_plugin/coordinator.py src/langharness_core/plugin.py src/langharness_core/plugins/agents/directory.py src/langharness_core/scopes.py tests/test_imports.py tests/test_runtime_mutation_coordinator.py tests/test_dynamic_plugin_e2e.py tests/test_scope_plugin_e2e.py tests/test_agent_directory.py tests/test_plugin_scope_classification.py
git commit -m "refactor: switch agent instance scope ids to agent:<id> colon format"
```

---

### Task 5: agent 模板 scope_parent 由 server 改为 root(拓扑 root→agent)

**Files:**
- Modify: `src/langharness_core/plugin.py`(4 处模板描述符)
- Modify: `src/langharness_plugin/coordinator.py:330`
- Modify: `tests/test_plugin_scope_classification.py`(templates 断言)
- Modify: `tests/test_core_descriptors.py:154-155`
- Modify: `tests/test_agent_directory.py:81-85,190-193`
- Modify: `tests/test_scope_plugin_e2e.py:299-306`
- Modify: `tests/test_runtime_mutation_coordinator.py:71-83`(fixture 一致性)

- [ ] **Step 1: 修改 core/plugin.py 的 4 处模板描述符**

`src/langharness_core/plugin.py` 中恰好 4 处如下两行对(agent 模板描述符),全部把 `scope_parent="server"` 改为 `scope_parent="root"`(可对这两行整体做 replace-all,注意 `scope="agent"` 配对的才是目标,server 描述符的 `scope_parent="root"` 不受影响):

```python
        scope="agent",
        scope_parent="server",
```

→

```python
        scope="agent",
        scope_parent="root",
```

(位于 `agent_plugin_template_descriptor`、`agent_loop_template_descriptor`、`tool_export_adapter_template_descriptor`、`dynamic_template_descriptor` 四个函数内。)

- [ ] **Step 2: 修改 coordinator 工具导出适配器的 scope_parent**

`src/langharness_plugin/coordinator.py` 第 330 行(Task 4 之后为):

```python
                scope_parent="agent" if target_scope.startswith("agent:") else "server",
```

改为:

```python
                scope_parent="agent" if target_scope.startswith("agent:") else str(ROOT_SCOPE_ID),
```

(该文件第 17 行已导入 `ROOT_SCOPE_ID`。)

- [ ] **Step 3: 更新分类与描述符测试**

`tests/test_plugin_scope_classification.py` 中 `test_agent_templates_and_instances_form_two_levels`:

```python
    assert {(item.scope, item.scope_parent) for item in templates} == {
        ("agent", "server")
    }
```

改为:

```python
    assert {(item.scope, item.scope_parent) for item in templates} == {
        ("agent", "root")
    }
```

`tests/test_core_descriptors.py` 第 154-155 行:

```python
        assert descriptor.scope == "agent"
        assert descriptor.scope_parent == "server"
```

改为:

```python
        assert descriptor.scope == "agent"
        assert descriptor.scope_parent == "root"
```

`tests/test_runtime_mutation_coordinator.py` 第 71-83 行 `agent_instance_package()` 中的 fixture:

```python
                descriptor("instance", scope="agent", scope_parent="server"),
```

改为:

```python
                descriptor("instance", scope="agent", scope_parent="root"),
```

- [ ] **Step 4: 更新 agent_directory 的假注册器与过滤器断言**

`tests/test_agent_directory.py` 第 81-85 行(FakeScopedRegistrar.ensure_scope 中的 server 特判):

```python
            wanted_parent = parent_id or ScopeId("root")
            if self.tree.get(wanted_parent) is None:
                if wanted_parent == ScopeId("agent"):
                    self.tree.create(ScopeId("server"), "server")
                    self.tree.create(wanted_parent, str(wanted_parent), ScopeId("server"))
                else:
                    self.tree.create(wanted_parent, str(wanted_parent))
            self.tree.create(scope_id, name, wanted_parent)
```

改为(agent 现在直接挂在 root 下,无需特判):

```python
            wanted_parent = parent_id or ScopeId("root")
            if self.tree.get(wanted_parent) is None:
                self.tree.create(wanted_parent, str(wanted_parent))
            self.tree.create(scope_id, name, wanted_parent)
```

同文件第 190-193 行:4 行过滤器字符串去掉 `(plugin.scope_id=server)` 子句(Task 4 之后为 `agent:simple_agent` 格式):

```python
        "_llm_provider": "(|(plugin.scope_id=agent:simple_agent)(plugin.scope_id=agent)(plugin.scope_id=server)(plugin.scope_id=root))",
        "_scoped_llm_providers": "(|(plugin.scope_id=agent:simple_agent)(plugin.scope_id=agent)(plugin.scope_id=server)(plugin.scope_id=root))",
        "_tool_providers": "(|(plugin.scope_id=agent:simple_agent)(plugin.scope_id=agent)(plugin.scope_id=server)(plugin.scope_id=root))",
        "_name_provider": "(|(plugin.scope_id=agent:simple_agent)(plugin.scope_id=agent)(plugin.scope_id=server)(plugin.scope_id=root))",
```

改为(4 行统一去掉 server 子句):

```python
        "_llm_provider": "(|(plugin.scope_id=agent:simple_agent)(plugin.scope_id=agent)(plugin.scope_id=root))",
        "_scoped_llm_providers": "(|(plugin.scope_id=agent:simple_agent)(plugin.scope_id=agent)(plugin.scope_id=root))",
        "_tool_providers": "(|(plugin.scope_id=agent:simple_agent)(plugin.scope_id=agent)(plugin.scope_id=root))",
        "_name_provider": "(|(plugin.scope_id=agent:simple_agent)(plugin.scope_id=agent)(plugin.scope_id=root))",
```

- [ ] **Step 5: 更新 scope e2e 的可见性断言**

`tests/test_scope_plugin_e2e.py` 第 299-306 行(Task 4 之后):

```python
        assert visible("agent") == {"root_other", "server_tool", "agent_tool"}
        assert visible("agent:a") == {
            "root_other",
            "server_tool",
            "agent_tool",
            "agent_a_tool",
        }
```

改为(agent 的祖先链变为 agent+root,server 工具不再可见):

```python
        assert visible("agent") == {"root_other", "agent_tool"}
        assert visible("agent:a") == {
            "root_other",
            "agent_tool",
            "agent_a_tool",
        }
```

(同测试中 `visible("root")`、`visible("ui")`、`visible("server")` 断言不变;`"agent_b_tool" not in visible("agent:a")` 与 `"ui_tool" not in visible("agent:a")` 不变。)

注意:`tests/test_dynamic_plugin_e2e.py` 的可见性断言**不需要改**:`tool_names(manager, "agent")` 里的 `server_echo` 来自挂在 agent scope 的工具导出适配器(不是 server 上的 echo 插件),拓扑变化后适配器仍在 agent scope,断言依旧成立。

- [ ] **Step 6: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_plugin_scope_classification.py tests/test_core_descriptors.py tests/test_agent_directory.py tests/test_scope_plugin_e2e.py tests/test_dynamic_plugin_e2e.py tests/test_runtime_mutation_coordinator.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/langharness_core/plugin.py src/langharness_plugin/coordinator.py tests/test_plugin_scope_classification.py tests/test_core_descriptors.py tests/test_agent_directory.py tests/test_scope_plugin_e2e.py tests/test_runtime_mutation_coordinator.py
git commit -m "feat: hang agent templates under root instead of server"
```

---

### Task 6: 恢复迁移 —— 已存在跳过 + 过滤旧格式 agent/<id>

**Files:**
- Modify: `src/langharness_plugin/coordinator.py:194-231,262-282`
- Test: `tests/test_runtime_mutation_coordinator.py`(新增 2 个测试)

- [ ] **Step 1: 写失败测试**

在 `tests/test_runtime_mutation_coordinator.py` 末尾追加:

```python
def test_restore_skips_legacy_and_preexisting_scopes() -> None:
    store = CountingStore()
    store.snapshot = RuntimeStateSnapshot(
        1,
        (
            {"id": "root", "parent_id": None, "name": "root"},
            {"id": "agent", "parent_id": "server", "name": "Agent"},
            {"id": "agent/a", "parent_id": "agent", "name": "A"},
        ),
        (),
    )
    runtime = manager()
    # The fake tree already carries the seeded built-in: agent under root.
    runtime.scope_tree.create(ScopeId("agent"), "Agent", ROOT_SCOPE_ID)
    mutations = RuntimeMutationCoordinator(
        runtime, store, PluginDiscovery(lambda: [])
    )

    assert mutations.restore() == ()

    ids = {scope.id for scope in runtime.scope_tree.snapshot().scopes}
    assert ScopeId("agent/a") not in ids
    assert runtime.scope_tree.get(ScopeId("agent")).parent_id == ROOT_SCOPE_ID


def test_restore_drops_legacy_agent_slash_registrations() -> None:
    store = CountingStore()
    legacy = PersistedPluginRegistration(
        "gone.package",
        "echo",
        "1",
        ScopeId("agent/a"),
        "echo",
        descriptor("echo"),
        True,
        "installed",
    )
    store.snapshot = RuntimeStateSnapshot(
        1,
        (
            {"id": "root", "parent_id": None, "name": "root"},
            {"id": "agent", "parent_id": "root", "name": "Agent"},
            {"id": "agent/a", "parent_id": "agent", "name": "A"},
        ),
        (legacy,),
    )
    runtime = manager()
    runtime.scope_tree.create(ScopeId("agent"), "Agent", ROOT_SCOPE_ID)
    mutations = RuntimeMutationCoordinator(
        runtime, store, PluginDiscovery(lambda: [])
    )

    assert mutations.restore() == ()
    assert mutations.registrations() == ()
    assert store.saves == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_runtime_mutation_coordinator.py::test_restore_skips_legacy_and_preexisting_scopes tests/test_runtime_mutation_coordinator.py::test_restore_drops_legacy_agent_slash_registrations -q`
Expected: FAIL(第一个:恢复时 `ensure_scope` 因父级冲突抛 ValueError;第二个:遗留注册被当作正常注册处理)

- [ ] **Step 3: 修改 _restore_scopes(已存在跳过 + 旧格式过滤)**

`src/langharness_plugin/coordinator.py` 第 262-282 行当前:

```python
    def _restore_scopes(self) -> None:
        pending = {
            ScopeId(str(item["id"])): item
            for item in self._loaded_scopes
            if item["id"] != str(ROOT_SCOPE_ID)
        }
        while pending:
            progressed = False
            for scope_id, item in tuple(pending.items()):
                parent = ScopeId(str(item["parent_id"]))
                if self.manager.scope_tree.get(parent) is None:
                    continue
                self.manager.ensure_scope(
                    scope_id,
                    name=str(item["name"]),
                    parent_id=parent,
                )
                pending.pop(scope_id)
                progressed = True
            if not progressed:
                raise RuntimeMutationError("Persisted scope tree contains an orphan")
```

改为:

```python
    def _restore_scopes(self) -> None:
        pending = {
            ScopeId(str(item["id"])): item
            for item in self._loaded_scopes
            if item["id"] != str(ROOT_SCOPE_ID)
            and not str(item["id"]).startswith("agent/")
        }
        while pending:
            progressed = False
            for scope_id, item in tuple(pending.items()):
                if self.manager.scope_tree.get(scope_id) is not None:
                    pending.pop(scope_id)
                    progressed = True
                    continue
                parent = ScopeId(str(item["parent_id"]))
                if self.manager.scope_tree.get(parent) is None:
                    continue
                self.manager.ensure_scope(
                    scope_id,
                    name=str(item["name"]),
                    parent_id=parent,
                )
                pending.pop(scope_id)
                progressed = True
            if not progressed:
                raise RuntimeMutationError("Persisted scope tree contains an orphan")
```

- [ ] **Step 4: 修改 restore() 丢弃旧格式注册**

`src/langharness_plugin/coordinator.py` 第 199-201 行当前:

```python
            self._restore_scopes()
            changed = False
            restored: list[PersistedPluginRegistration] = []
```

改为:

```python
            self._restore_scopes()
            changed = False
            kept: list[PersistedPluginRegistration] = []
            for registration in self._registrations:
                if str(registration.scope_id).startswith("agent/"):
                    changed = True
                    continue
                kept.append(registration)
            self._registrations = kept
            restored: list[PersistedPluginRegistration] = []
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_runtime_mutation_coordinator.py -q`
Expected: PASS(含既有 orphan 测试 —— 其快照里 `agent:a` 的父级 `agent` 在假树中不存在,依旧报 orphan)

- [ ] **Step 6: Commit**

```bash
git add src/langharness_plugin/coordinator.py tests/test_runtime_mutation_coordinator.py
git commit -m "feat: self-heal restore skips preexisting scopes and legacy agent/<id> data"
```

---

### Task 7: API GET /scope 路由

**Files:**
- Modify: `src/langharness_plugin/contracts.py`(DynamicPluginManager 加 `scopes()`)
- Modify: `src/langharness_plugin/coordinator.py`(实现 `scopes()`)
- Create: `src/langharness_api/plugins/routes/scopes.py`
- Modify: `src/langharness_api/plugin.py`(描述符 + 贡献项)
- Modify: `tests/test_plugin_scope_classification.py`(server 列表加入 api_scopes)
- Modify: `tests/test_imports.py`(加入 routes.scopes)
- Test: `tests/test_scope_routes.py`(新)

- [ ] **Step 1: 扩展协议并写失败测试**

`src/langharness_plugin/contracts.py` 导入处:

```python
from langharness_scope import ScopeId
```

改为:

```python
from langharness_scope import Scope, ScopeId
```

`DynamicPluginManager` 协议末尾(`upgrade` 之后)加:

```python
    def scopes(self) -> tuple[Scope, ...]: ...
```

创建 `tests/test_scope_routes.py`:

```python
"""Tests for the scope tree route."""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from langharness_api.plugins.routes.scopes import ScopesRoutePlugin
from langharness_scope import Scope, ScopeId


class FakeDynamic:
    def rescan(self) -> Any:
        return None

    def discovered(self) -> tuple[Any, ...]:
        return ()

    def registrations(self) -> tuple[Any, ...]:
        return ()

    def install(self, package_id, contribution_id, *, scope_id=None):
        raise NotImplementedError

    def set_enabled(self, name, enabled):
        raise NotImplementedError

    def uninstall(self, name):
        raise NotImplementedError

    def upgrade(self, name):
        raise NotImplementedError

    def scopes(self) -> tuple[Scope, ...]:
        return (
            Scope(ScopeId("root"), None, "root"),
            Scope(ScopeId("ui"), ScopeId("root"), "UI"),
            Scope(ScopeId("agent"), ScopeId("root"), "Agent"),
            Scope(ScopeId("agent:a"), ScopeId("agent"), "A"),
        )


def make_plugin() -> ScopesRoutePlugin:
    plugin = ScopesRoutePlugin()
    plugin._dynamic = FakeDynamic()
    return plugin


def make_client(plugin: ScopesRoutePlugin) -> TestClient:
    app = FastAPI()
    app.include_router(plugin.get_router())
    return TestClient(app)


def test_get_scope_returns_the_tree() -> None:
    response = make_client(make_plugin()).get("/scope")
    assert response.status_code == 200
    assert response.json() == {
        "scopes": [
            {"id": "root", "parent_id": None, "name": "root"},
            {"id": "ui", "parent_id": "root", "name": "UI"},
            {"id": "agent", "parent_id": "root", "name": "Agent"},
            {"id": "agent:a", "parent_id": "agent", "name": "A"},
        ]
    }


def test_get_scope_returns_503_without_dynamic_manager() -> None:
    plugin = ScopesRoutePlugin()
    response = make_client(plugin).get("/scope")
    assert response.status_code == 503


def test_plugin_info_is_exposed() -> None:
    assert make_plugin().get_plugin_info() == {"name": "scopes", "version": "1.0.0"}
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_scope_routes.py -q`
Expected: FAIL,`ModuleNotFoundError: No module named 'langharness_api.plugins.routes.scopes'`

- [ ] **Step 3: coordinator 实现 scopes()**

`src/langharness_plugin/coordinator.py` 导入:

```python
from langharness_scope import ROOT_SCOPE_ID, ScopeId
```

改为:

```python
from langharness_scope import ROOT_SCOPE_ID, Scope, ScopeId
```

`registrations()` 之后加:

```python
    def scopes(self) -> tuple[Scope, ...]:
        """Current scope tree snapshot for read-only consumers."""
        return self.manager.scope_tree.snapshot().scopes
```

- [ ] **Step 4: 创建路由插件**

创建 `src/langharness_api/plugins/routes/scopes.py`:

```python
"""Scope tree route: the runtime scope hierarchy."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Property,
    Provides,
    RequiresBest,
    UnbindField,
)

from langharness_api.common.errors import http_error
from langharness_api.contracts import RouteProvider
from langharness_plugin.contracts import DynamicPluginManager
from langharness_plugin.validation import ContractGuard


@ComponentFactory("api-scopes-route-factory")
@Provides(RouteProvider)
@Property("_plugin_name", "plugin.name", "scopes")
@Property("_plugin_version", "plugin.version", "1.0.0")
@RequiresBest("_dynamic", DynamicPluginManager, optional=True, immediate_rebind=True)
class ScopesRoutePlugin:
    """Serves the runtime scope tree."""

    def __init__(self) -> None:
        self._plugin_name = "scopes"
        self._plugin_version = "1.0.0"
        self._dynamic: Any = None
        self._guards: dict[str, ContractGuard] = {
            "_dynamic": ContractGuard(self, "_dynamic", DynamicPluginManager),
        }

    @BindField("_dynamic", if_valid=True)
    def _on_dynamic_bind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].admit(service)

    @UnbindField("_dynamic", if_valid=True)
    def _on_dynamic_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].release(service)

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/scope")
        def read_scope() -> dict[str, Any]:
            dynamic = self._require_dynamic()
            return {
                "scopes": [
                    {
                        "id": str(scope.id),
                        "parent_id": (
                            str(scope.parent_id)
                            if scope.parent_id is not None
                            else None
                        ),
                        "name": scope.name,
                    }
                    for scope in dynamic.scopes()
                ]
            }

        return router

    def _require_dynamic(self) -> Any:
        if self._dynamic is None:
            raise http_error(
                503,
                "Dynamic plugin manager unavailable",
                code="SERVICE_UNAVAILABLE",
                error_type="ServiceUnavailable",
            )
        return self._dynamic

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
```

- [ ] **Step 5: 注册描述符与贡献项**

`src/langharness_api/plugin.py` 在 `api_plugins_descriptor` 之后新增:

```python
def api_scopes_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="api-scopes",
        version="1.0.0",
        module="langharness_api.plugins.routes.scopes",
        factory="api-scopes-route-factory",
        instance="api-scopes",
        specification=SPEC_ROUTE,
        scope="server",
        scope_parent="root",
    )
```

`builtin_package()` 的 contributions 里,`PluginContribution("plugins", "server", api_plugins_descriptor(directory)),` 之后插入:

```python
            PluginContribution("scopes", "server", api_scopes_descriptor()),
```

`tests/test_plugin_scope_classification.py`:导入列表加 `api_scopes_descriptor`,并在 `test_server_plugins_and_checkpointer_are_in_server_scope` 的 descriptors 列表里(如 `api_plugins_descriptor("/tmp/config"),` 之后)加 `api_scopes_descriptor(),`。

`tests/test_imports.py` 在 `"langharness_api.plugins.routes.plugins",` 与 `"langharness_api.plugins.routes.sessions",` 之间插入 `"langharness_api.plugins.routes.scopes",`。

- [ ] **Step 6: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_scope_routes.py tests/test_plugin_scope_classification.py tests/test_runtime_mutation_coordinator.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/langharness_plugin/contracts.py src/langharness_plugin/coordinator.py src/langharness_api/plugins/routes/scopes.py src/langharness_api/plugin.py tests/test_scope_routes.py tests/test_plugin_scope_classification.py tests/test_imports.py
git commit -m "feat: serve the runtime scope tree at GET /scope"
```

---

### Task 8: CLI /scope 交互命令

**Files:**
- Create: `src/langharness_cli/plugins/commands/scope.py`
- Modify: `src/langharness_cli/plugin.py`(描述符 + 贡献项)
- Modify: `tests/test_cli.py:374-381`(安装集合加 cli-scope)
- Modify: `tests/test_imports.py`(加入 commands.scope)
- Test: `tests/test_scope_command.py`(新)

- [ ] **Step 1: 写失败测试**

创建 `tests/test_scope_command.py`:

```python
"""Tests for the scope tree command plugin."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from langharness_cli.plugins.commands.scope import ScopeCommandPlugin

SCOPE_PAYLOAD = {
    "scopes": [
        {"id": "root", "parent_id": None, "name": "root"},
        {"id": "ui", "parent_id": "root", "name": "UI"},
        {"id": "server", "parent_id": "root", "name": "Server"},
        {"id": "agent", "parent_id": "root", "name": "Agent"},
        {"id": "agent:a", "parent_id": "agent", "name": "A"},
    ]
}


class Context:
    def __init__(self) -> None:
        self.base_url = "http://api"
        self.token = "secret"

    def refresh_status(self) -> None:
        return None


class Response:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://api/scope")
            raise httpx.HTTPStatusError(
                str(self._payload),
                request=request,
                response=httpx.Response(self.status_code, json=self._payload),
            )


def make_plugin() -> ScopeCommandPlugin:
    return ScopeCommandPlugin()


def test_scope_exposes_command_specs() -> None:
    plugin = make_plugin()
    assert [item.name for item in plugin.get_commands()] == ["scope"]
    assert [item.name for item in plugin.get_interactive_commands()] == ["scope"]
    assert plugin.get_plugin_info() == {"name": "scope-command", "version": "1.0.0"}


def test_scope_renders_indented_tree(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plugin = make_plugin()
    monkeypatch.setattr(httpx, "get", lambda *a, **k: Response(SCOPE_PAYLOAD))
    command = {item.name: item for item in plugin.get_interactive_commands()}["scope"]

    assert command.handler(Context(), "") is False

    output = capsys.readouterr().out
    assert output.splitlines() == [
        "root",
        "├── agent",
        "│   └── agent:a",
        "├── server",
        "└── ui",
    ]


def test_scope_prints_json_for_noninteractive_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plugin = make_plugin()
    monkeypatch.setattr(httpx, "get", lambda *a, **k: Response(SCOPE_PAYLOAD))
    command = plugin.get_commands()[0]

    assert command.handler(type("Args", (), {})()) == 0
    assert '"scopes"' in capsys.readouterr().out


def test_scope_reports_request_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plugin = make_plugin()
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: Response({"detail": "boom"}, status_code=503)
    )
    command = {item.name: item for item in plugin.get_interactive_commands()}["scope"]

    assert command.handler(Context(), "") is False
    assert "Scope request failed" in capsys.readouterr().out
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_scope_command.py -q`
Expected: FAIL,`ModuleNotFoundError: No module named 'langharness_cli.plugins.commands.scope'`

- [ ] **Step 3: 实现命令插件**

创建 `src/langharness_cli/plugins/commands/scope.py`:

```python
"""Scope tree command plugin."""

from __future__ import annotations

import json
from argparse import Namespace
from typing import Any

import httpx
from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharness_cli.contracts import (
    CLICommandProvider,
    CommandSpec,
    InteractiveCommandContext,
    InteractiveCommandSpec,
)


@ComponentFactory("cli-scope-command-factory")
@Provides(CLICommandProvider)
@Property("_plugin_name", "plugin.name", "scope-command")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_base_url", "plugin.base_url", "http://127.0.0.1:11534")
@Property("_token", "plugin.token", "secret")
class ScopeCommandPlugin:
    """Shows the runtime scope tree served by the API."""

    def __init__(self) -> None:
        self._plugin_name = "scope-command"
        self._plugin_version = "1.0.0"
        self._base_url = "http://127.0.0.1:11534"
        self._token = "secret"

    def get_commands(self) -> list[CommandSpec]:
        return [
            CommandSpec(
                name="scope",
                help="Show the runtime scope tree",
                handler=self._handler,
            )
        ]

    def get_interactive_commands(self) -> list[InteractiveCommandSpec]:
        return [
            InteractiveCommandSpec(
                name="scope",
                help="Show the runtime scope tree",
                handler=self._interactive_handler,
            )
        ]

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}

    def _handler(self, args: Namespace) -> int:
        try:
            payload = self._get(
                f"{self._base_url.rstrip('/')}/scope", self._token
            )
        except httpx.HTTPError as exc:
            print(f"Scope request failed: {exc}")
            return 1
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    def _interactive_handler(
        self, context: InteractiveCommandContext, line: str
    ) -> bool:
        try:
            payload = self._get(
                f"{context.base_url.rstrip('/')}/scope", context.token
            )
        except httpx.HTTPError as exc:
            print(f"Scope request failed: {exc}")
            return False
        print(_render_tree(payload.get("scopes") or []))
        return False

    @staticmethod
    def _get(base_url: str, token: str) -> dict[str, Any]:
        response = httpx.get(
            base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        response.raise_for_status()
        return dict(response.json())


def _render_tree(scopes: list[dict[str, Any]]) -> str:
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

- [ ] **Step 4: 注册描述符与贡献项**

`src/langharness_cli/plugin.py` 的 `cli_descriptors()` 列表末尾(`cli-shell` 描述符之后)加:

```python
        PluginDescriptor(
            name="cli-scope",
            version="1.0.0",
            module="langharness_cli.plugins.commands.scope",
            factory="cli-scope-command-factory",
            instance="cli-scope",
            specification=SPEC_CLI_COMMAND,
            properties={"plugin.ui.locale": locale},
            scope="ui",
            scope_parent="root",
        ),
```

`builtin_package()` 的 `contribution_ids` 元组末尾加 `"scope"`:

```python
    contribution_ids = (
        "server",
        "health",
        "model",
        "rich-renderer",
        "session",
        "plugins",
        "scope",
        "shell",
    )
```

- [ ] **Step 5: 更新既有断言**

`tests/test_cli.py` 第 374-381 行的安装集合:

```python
    assert {descriptor.name for descriptor in installed} == {
        "cli-health",
        "cli-log",
        "cli-model",
        "cli-plugins",
        "cli-rich-renderer",
        "cli-session",
        "cli-shell",
        "config-toml",
            "configs",
            "ui-server",
        }
```

改为(加 `"cli-scope",`):

```python
    assert {descriptor.name for descriptor in installed} == {
        "cli-health",
        "cli-log",
        "cli-model",
        "cli-plugins",
        "cli-rich-renderer",
        "cli-scope",
        "cli-session",
        "cli-shell",
        "config-toml",
            "configs",
            "ui-server",
        }
```

(注意保留文件中已有的 `"configs",` 与 `"ui-server",` 缩进原样。)

`tests/test_imports.py` 在 `"langharness_cli.plugins.commands.plugins",` 与 `"langharness_cli.plugins.commands.session",` 之间插入 `"langharness_cli.plugins.commands.scope",`。

- [ ] **Step 6: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_scope_command.py tests/test_cli.py tests/test_plugin_scope_classification.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/langharness_cli/plugins/commands/scope.py src/langharness_cli/plugin.py tests/test_scope_command.py tests/test_cli.py tests/test_imports.py
git commit -m "feat: add /scope command showing the runtime scope tree"
```

---

### Task 9: 全量验证

**Files:** 无

- [ ] **Step 1: 依次跑与 pre-commit 钩子相同的全部检查**

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
.venv/bin/python -m pyright --pythonpath .venv/bin/python
.venv/bin/python -m pytest tests/test_imports.py -q
.venv/bin/python -m pytest -q --cov=langharness --cov=langharness_scope --cov=langharness_config --cov=langharness_logging --cov=langharness_core --cov=langharness_plugin --cov=langharness_api --cov=langharness_cli --cov-report=term-missing --cov-fail-under=95
```

Expected: 全部通过;coverage ≥ 95%(删除 `langharness_core/scopes.py` 后基准约 96.3%,新增文件均有测试覆盖)。

- [ ] **Step 2: 人工冒烟(可选,需运行中的服务)**

启动服务端(另一终端):`.venv/bin/python -m langharness --mode server --config-dir /tmp/smoke`
然后 `curl -H "Authorization: Bearer secret" http://127.0.0.1:11534/scope`,预期返回含 root/ui/server/agent 的 JSON;在交互模式里输入 `/scope`,预期输出缩进树。

- [ ] **Step 3: 若 Step 1 全绿,无需再 commit(每个任务已各自提交);否则修复后按对应任务补 commit。**
