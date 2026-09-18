# Plugin 操作强制 Scope 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让所有 plugin 变更操作强制指定 scope（未指定报错提示），list/config 未指定 scope 时聚合展示所有 scope，并修复 API 层按插件名全局查找导致命中错误 scope 插件的根因。

**Architecture:** 三层贯通：`RuntimeMutationCoordinator` 按 `(scope_id, name)` 精确查找注册项；API runtime 变更端点接收必填 `scope` 查询参数并校验；CLI（非交互 `plugins` 命令 + 交互式 `/plugins` 命令）对变更操作强制 scope 并校验格式。list/config 无 scope 时 API 已聚合，本计划补 CLI 校验与 Scope 展示列。

**Tech Stack:** Python 3.13、FastAPI、httpx、Pelix iPOPO、pytest、ruff、mypy(strict)

## Global Constraints

- 设计文档：`docs/designs/2026-09-17-plugin-scope-enforcement-design.md`（本计划的唯一权威来源）
- runtime scope 词汇表：`root` / `server` / `ui` / `agent` / `agent:<id>`
- config scope 词汇表：`api` / `cli` / `agent:<id>`
- 变更操作缺 scope：错误信息 + usage；非交互退出码 1，交互式返回 REPL（返回 False）
- 提交必须使用**精确路径** `git add`，**绝不提交** `.vscode/launch.json` 与 `src/langharness_core/plugins/system_prompt/template_system_prompt.py`（工作区中与本次无关的未提交改动）
- **工作区基线**（未提交的本次特性相关改动，随各任务提交）：CLI/API 已做了部分 scope 透传与 config 聚合、usage 已更新；`tests/test_plugin_commands.py` 当前有 2 个失败（`test_noninteractive_enable_disable_upgrade_uninstall`、`test_plugins_lists_runtime_plugins_for_default_scope`），分别在 Task 3 / Task 5 修复
- mypy strict 覆盖 `src`；协调器签名必须与协议完全一致（`ContractGuard` 会做签名内省校验，keyword-only 参数两边必须一致）

---

### Task 1: 协调器按 (scope_id, name) 精确查找

**Files:**
- Modify: `src/langharness_plugin/contracts.py:83-93`
- Modify: `src/langharness_plugin/coordinator.py:108-228, 332-338`
- Test: `tests/test_runtime_mutation_coordinator.py`（全部变更调用补 `scope_id`，新增同名跨 scope 用例）
- Test: `tests/test_dynamic_plugin_e2e.py:207-220`（协调器调用补 `scope_id`）

**Interfaces:**
- Consumes: `ScopeId`（`langharness_scope.model`，`NewType("ScopeId", str)`，已在此两文件导入）
- Produces:
  - `RuntimeMutationCoordinator.set_enabled(name: str, enabled: bool, *, scope_id: ScopeId) -> PersistedPluginRegistration`
  - `RuntimeMutationCoordinator.update_properties(name: str, properties: dict[str, object], *, scope_id: ScopeId) -> PersistedPluginRegistration`
  - `RuntimeMutationCoordinator.uninstall(name: str, *, scope_id: ScopeId) -> None`
  - `RuntimeMutationCoordinator.upgrade(name: str, *, scope_id: ScopeId) -> PersistedPluginRegistration`
  - 未匹配时抛 `KeyError(f"plugin {name} not found in scope {scope_id}")`
- 协议 `DynamicPluginManager` 四个方法同步改为带必填 keyword-only `scope_id: ScopeId`

- [ ] **Step 1: 更新协调器测试调用并新增失败用例**

`tests/test_runtime_mutation_coordinator.py` 中所有变更调用补 `scope_id=ScopeId("server")`（测试 helper `descriptor()` 默认 `scope="server"`，故安装后注册项的 `scope_id` 为 `ScopeId("server")`），逐处替换：

- 行 226/228/230（`test_each_successful_mutation_persists_exactly_once`）：

```python
    mutations.install("dynamic.package", "dynamic")
    assert store.saves == 1
    mutations.set_enabled("dynamic", False, scope_id=ScopeId("server"))
    assert store.saves == 2
    mutations.set_enabled("dynamic", True, scope_id=ScopeId("server"))
    assert store.saves == 3
    mutations.uninstall("dynamic", scope_id=ScopeId("server"))
    assert store.saves == 4
```

- 行 326/330（`test_enable_installs_adapters_and_disable_kills_them`）：

```python
    mutations.set_enabled("export", False, scope_id=ScopeId("server"))
```

```python
    mutations.set_enabled("export", True, scope_id=ScopeId("server"))
```

- 行 342/356（upgrade 两个用例）、行 385（rollback 用例）：

```python
    updated = mutations.upgrade("dynamic", scope_id=ScopeId("server"))
```

- 行 369（`test_update_properties_replaces_plugin_and_persists`）：

```python
    updated = mutations.update_properties(
        "dynamic", {"plugin.value": "new"}, scope_id=ScopeId("server")
    )
```

- 行 398（`test_uninstall_persistence_failure_rolls_back_runtime`）：

```python
        mutations.uninstall("dynamic", scope_id=ScopeId("server"))
```

- 行 404-414（`test_unknown_mutation_targets_raise_key_error`）：

```python
    with pytest.raises(KeyError):
        mutations.set_enabled("nope", True, scope_id=ScopeId("server"))
    with pytest.raises(KeyError):
        mutations.upgrade("nope", scope_id=ScopeId("server"))
    with pytest.raises(KeyError):
        mutations.uninstall("nope", scope_id=ScopeId("server"))
```

- 行 645/656/660/674（set_enabled 相关用例）：

```python
    current = mutations.set_enabled("dynamic", True, scope_id=ScopeId("server"))
```

```python
    mutations.set_enabled("dynamic", False, scope_id=ScopeId("server"))
```

```python
        mutations.set_enabled("dynamic", True, scope_id=ScopeId("server"))
```

```python
        mutations.set_enabled("dynamic", False, scope_id=ScopeId("server"))
```

- 行 693（`test_upgrade_with_adapters_installs_them`）：

```python
    updated = mutations.upgrade("export", scope_id=ScopeId("server"))
```

- 文件末尾新增用例：

```python
def test_same_name_in_two_scopes_targets_only_the_given_scope() -> None:
    server_reg = PersistedPluginRegistration(
        "dynamic.package", "dynamic", "1", ScopeId("server"), "dynamic",
        descriptor("dynamic"), True, "installed",
    )
    ui_reg = PersistedPluginRegistration(
        "dynamic.package", "dynamic", "1", ScopeId("ui"), "dynamic",
        descriptor("dynamic", scope="ui"), True, "installed",
    )
    store = CountingStore()
    store.snapshot = RuntimeStateSnapshot(
        1,
        (
            {"id": "root", "parent_id": None, "name": "root"},
            {"id": "server", "parent_id": "root", "name": "server"},
            {"id": "ui", "parent_id": "root", "name": "ui"},
        ),
        (server_reg, ui_reg),
    )
    runtime = manager()
    runtime.registry.add(descriptor("dynamic"))
    runtime.bound.add("dynamic")
    mutations = RuntimeMutationCoordinator(runtime, store, PluginDiscovery(lambda: []))

    updated = mutations.set_enabled("dynamic", False, scope_id=ScopeId("server"))

    assert updated.scope_id == ScopeId("server")
    assert mutations.registrations()[0].enabled is False
    assert mutations.registrations()[1].enabled is True

    with pytest.raises(KeyError, match="not found in scope"):
        mutations.set_enabled("dynamic", False, scope_id=ScopeId("agent"))
```

`tests/test_dynamic_plugin_e2e.py` 行 207-220 补 `scope_id`（`echo_descriptor` 的 `scope="server"`；`ScopeId` 已在行 21 导入）：

```python
        disabled = coordinator.set_enabled(
            "server-echo", False, scope_id=ScopeId("server")
        )
        assert disabled.enabled is False
        assert "server_echo" not in tool_names(manager, "agent")

        enabled = coordinator.set_enabled(
            "server-echo", True, scope_id=ScopeId("server")
        )
        assert enabled.enabled is True
        assert "server_echo" in tool_names(manager, "agent")

        coordinator._catalog["example.echo"] = server_echo_package("1.1.0")
        upgraded = coordinator.upgrade("server-echo", scope_id=ScopeId("server"))
        assert upgraded.package_version == "1.1.0"
        assert upgraded.descriptor.version == "1.1.0"

        coordinator.uninstall("server-echo", scope_id=ScopeId("server"))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_runtime_mutation_coordinator.py -q`
Expected: FAIL，报 `TypeError: set_enabled() got an unexpected keyword argument 'scope_id'`（或 `missing 1 required keyword-only argument: 'scope_id'`）

- [ ] **Step 3: 修改协议与协调器**

`src/langharness_plugin/contracts.py` 行 83-93 替换为：

```python
    def set_enabled(
        self, name: str, enabled: bool, *, scope_id: ScopeId
    ) -> PersistedPluginRegistration: ...

    def update_properties(
        self, name: str, properties: dict[str, Any], *, scope_id: ScopeId
    ) -> PersistedPluginRegistration: ...

    def uninstall(self, name: str, *, scope_id: ScopeId) -> None: ...

    def upgrade(
        self, name: str, *, scope_id: ScopeId
    ) -> PersistedPluginRegistration: ...
```

`src/langharness_plugin/coordinator.py`：

- `set_enabled` 签名与查找（行 108-110）：

```python
    def set_enabled(
        self, name: str, enabled: bool, *, scope_id: ScopeId
    ) -> PersistedPluginRegistration:
        with self._lock:
            index, current = self._registration(name, scope_id)
```

- `update_properties` 签名与查找（行 147-152）：

```python
    def update_properties(
        self, name: str, properties: dict[str, object], *, scope_id: ScopeId
    ) -> PersistedPluginRegistration:
        """Replace a dynamic instance with merged properties and persist it."""
        with self._lock:
            index, current = self._registration(name, scope_id)
```

- `upgrade` 签名与查找（行 179-181）：

```python
    def upgrade(self, name: str, *, scope_id: ScopeId) -> PersistedPluginRegistration:
        with self._lock:
            index, current = self._registration(name, scope_id)
```

- `uninstall` 签名与查找（行 211-213）：

```python
    def uninstall(self, name: str, *, scope_id: ScopeId) -> None:
        with self._lock:
            index, current = self._registration(name, scope_id)
```

- `_registration`（行 332-338）替换为：

```python
    def _registration(
        self, name: str, scope_id: ScopeId
    ) -> tuple[int, PersistedPluginRegistration]:
        for index, registration in enumerate(self._registrations):
            if (
                registration.descriptor.name == name
                and registration.scope_id == scope_id
            ):
                return index, registration
        raise KeyError(f"plugin {name} not found in scope {scope_id}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_runtime_mutation_coordinator.py tests/test_dynamic_plugin_e2e.py -q`
Expected: PASS

- [ ] **Step 5: 类型检查**

Run: `python -m mypy src/langharness_plugin`
Expected: 无错误（协议与实现签名一致）

- [ ] **Step 6: 提交**

```bash
git add src/langharness_plugin/contracts.py src/langharness_plugin/coordinator.py tests/test_runtime_mutation_coordinator.py tests/test_dynamic_plugin_e2e.py
git commit -m "feat: scope-aware runtime mutation lookup in coordinator"
```

---

### Task 2: API runtime 变更端点强制 scope

**Files:**
- Modify: `src/langharness_api/plugins/routes/plugins.py:21-27, 192-254, 302-322`
- Test: `tests/test_plugin_config_routes.py:115-151, 433-533`（FakeDynamic 签名 + 既有用例更新 + 新用例）

**Interfaces:**
- Consumes: Task 1 的协调器签名（`set_enabled(name, enabled, *, scope_id)` 等）；`operation_error`（`langharness_api/common/errors.py`，KeyError 时 `status_code=404` 且 code 为 `PLUGIN_NOT_FOUND`）
- Produces:
  - 路由插件私有方法 `_validate_runtime_scope(self, scope: str) -> None`（非法抛 400 `Unknown runtime scope: {scope}`）
  - 四个 runtime 变更端点新增必填 `scope: str = Query(...)`
  - 未匹配时 404，detail 形如 `'plugin x not found in scope server'`
  - `GET /plugins/runtime` 传 scope 时先 `_validate_runtime_scope`

- [ ] **Step 1: 更新路由测试（先写失败测试）**

`tests/test_plugin_config_routes.py`：

- `FakeDynamic`（行 115-151）替换四个方法与记录类型：

```python
class FakeDynamic:
    def __init__(self) -> None:
        self.packages = (FakePackage("example.package", "1"),)
        self.failures = ()
        self.registrations_list = (FakeRegistration("echo"),)
        self.installs: list[tuple[str, str, str | None]] = []
        self.enabled: list[tuple[str, bool, str | None]] = []
        self.uninstalled: list[tuple[str, str | None]] = []
        self.upgraded: list[tuple[str, str | None]] = []

    def discovered(self):
        return self.packages

    def rescan(self):
        return self

    def registrations(self):
        return self.registrations_list

    def install(self, package_id, contribution_id, *, scope_id=None):
        self.installs.append((package_id, contribution_id, scope_id))
        return FakeRegistration(f"{contribution_id}@{scope_id or 'server'}")

    def set_enabled(self, name, enabled, *, scope_id=None):
        self.enabled.append((name, enabled, str(scope_id) if scope_id else None))
        return FakeRegistration(name)

    def update_properties(self, name, properties, *, scope_id=None):
        self.properties = (name, properties, str(scope_id) if scope_id else None)
        return FakeRegistration(name)

    def uninstall(self, name, *, scope_id=None):
        self.uninstalled.append((name, str(scope_id) if scope_id else None))

    def upgrade(self, name, *, scope_id=None):
        self.upgraded.append((name, str(scope_id) if scope_id else None))
        return FakeRegistration(name)

    def scopes(self):
        return ()
```

- `test_dynamic_runtime_install_enable_upgrade_uninstall`（行 433-472）替换为：

```python
def test_dynamic_runtime_install_enable_upgrade_uninstall(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    client = make_client(plugin)

    runtime = client.get("/plugins/runtime")
    assert runtime.status_code == 200
    assert runtime.json()["plugins"][0]["name"] == "echo"

    install = client.post(
        "/plugins/install",
        json={
            "package_id": "example.package",
            "contribution_id": "echo",
            "scope_id": "server",
        },
    )
    assert install.status_code == 200
    assert install.json()["name"] == "echo@server"
    assert plugin._dynamic.installs == [("example.package", "echo", "server")]

    enable = client.put(
        "/plugins/runtime/echo/enabled",
        json={"enabled": False},
        params={"scope": "server"},
    )
    assert enable.status_code == 200
    assert plugin._dynamic.enabled == [("echo", False, "server")]

    properties = client.put(
        "/plugins/runtime/echo/properties",
        json={"properties": {"plugin.value": "x"}},
        params={"scope": "server"},
    )
    assert properties.status_code == 200
    assert plugin._dynamic.properties == ("echo", {"plugin.value": "x"}, "server")

    upgrade = client.post("/plugins/runtime/echo/upgrade", params={"scope": "server"})
    assert upgrade.status_code == 200
    assert plugin._dynamic.upgraded == [("echo", "server")]

    delete = client.delete("/plugins/runtime/echo", params={"scope": "server"})
    assert delete.status_code == 200
    assert delete.json() == {"removed": True}
    assert plugin._dynamic.uninstalled == [("echo", "server")]
```

- `test_dynamic_endpoints_require_dynamic_manager`（行 490-505）的 runtime 三项补 `params`：

```python
    for method, path, kwargs in [
        ("get", "/plugins/discovered", {}),
        ("post", "/plugins/rescan", {}),
        ("get", "/plugins/runtime", {}),
        ("post", "/plugins/install", {"json": {"package_id": "p", "contribution_id": "c"}}),
        ("put", "/plugins/runtime/x/enabled", {"json": {"enabled": True}, "params": {"scope": "server"}}),
        ("delete", "/plugins/runtime/x", {"params": {"scope": "server"}}),
        ("post", "/plugins/runtime/x/upgrade", {"params": {"scope": "server"}}),
    ]:
```

- `test_dynamic_endpoints_report_errors`（行 508-532）末尾三行替换为：

```python
    assert client.put(
        "/plugins/runtime/x/enabled",
        json={"enabled": True},
        params={"scope": "server"},
    ).status_code == 404
    assert client.delete(
        "/plugins/runtime/x", params={"scope": "server"}
    ).status_code == 404
    assert client.post(
        "/plugins/runtime/x/upgrade", params={"scope": "server"}
    ).status_code == 404
```

（install 断言保持 400 不变，install 端点未改。）

- 文件末尾新增三个用例：

```python
def test_runtime_mutations_require_scope(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    client = make_client(plugin)

    assert client.put(
        "/plugins/runtime/x/enabled", json={"enabled": True}
    ).status_code == 422
    assert client.put(
        "/plugins/runtime/x/properties", json={"properties": {}}
    ).status_code == 422
    assert client.delete("/plugins/runtime/x").status_code == 422
    assert client.post("/plugins/runtime/x/upgrade").status_code == 422


def test_runtime_mutations_reject_unknown_scope(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    client = make_client(plugin)

    response = client.put(
        "/plugins/runtime/x/enabled",
        json={"enabled": True},
        params={"scope": "mars"},
    )
    assert response.status_code == 400
    assert "Unknown runtime scope: mars" in response.json()["detail"]


def test_runtime_list_rejects_unknown_scope(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    client = make_client(plugin)

    response = client.get("/plugins/runtime", params={"scope": "mars"})
    assert response.status_code == 400
    assert "Unknown runtime scope: mars" in response.json()["detail"]


def test_runtime_mutation_not_found_in_scope_returns_404(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)

    def fail(*args, **kwargs):
        raise KeyError("plugin echo not found in scope server")

    plugin._dynamic.set_enabled = fail
    client = make_client(plugin)

    response = client.put(
        "/plugins/runtime/echo/enabled",
        json={"enabled": False},
        params={"scope": "server"},
    )
    assert response.status_code == 404
    assert "not found in scope" in response.json()["detail"]
    assert response.headers["x-error-code"] == "PLUGIN_NOT_FOUND"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_plugin_config_routes.py -q`
Expected: FAIL——`test_dynamic_runtime_install_enable_upgrade_uninstall` 报 `422`（FastAPI 尚未声明 scope 参数时多余 query 参数被忽略，实际是断言 `plugin._dynamic.enabled == [("echo", False, "server")]` 失败，因端点还没传 scope）；`test_runtime_mutations_require_scope` 期望 422 却得到 200

- [ ] **Step 3: 修改 API 路由**

`src/langharness_api/plugins/routes/plugins.py`：

- 导入区（行 21-27 附近）补一行（放在 `from langharness_plugin.contracts import ...` 之后）：

```python
from langharness_scope import ScopeId
```

- 常量（行 29 `KNOWN_SCOPES = ("api", "cli")` 之后）新增：

```python
KNOWN_RUNTIME_SCOPES = ("root", "server", "ui", "agent")
```

- `GET /plugins/runtime`（行 192-204）替换为：

```python
        @router.get("/plugins/runtime")
        def runtime_plugins(scope: str | None = Query(None)) -> dict[str, Any]:
            if scope is not None:
                self._validate_runtime_scope(scope)
            registrations = self._require_dynamic().registrations()
            if scope is not None:
                registrations = (
                    item for item in registrations if str(item.scope_id) == scope
                )
            return {
                "plugins": [
                    self._registration_payload(item)
                    for item in registrations
                ]
            }
```

- `PUT /plugins/runtime/{name}/enabled`（行 218-224）替换为：

```python
        @router.put("/plugins/runtime/{name}/enabled")
        def enable_plugin(
            name: str,
            enabled: bool = Body(..., embed=True),
            scope: str = Query(...),
        ) -> dict[str, Any]:
            self._validate_runtime_scope(scope)
            try:
                registration = self._require_dynamic().set_enabled(
                    name, enabled, scope_id=ScopeId(scope)
                )
            except KeyError as exc:
                raise operation_error(exc, status_code=404) from exc
            except (ValueError, RuntimeError) as exc:
                raise operation_error(exc) from exc
            return self._registration_payload(registration)
```

- `PUT /plugins/runtime/{name}/properties`（行 226-236）替换为：

```python
        @router.put("/plugins/runtime/{name}/properties")
        def update_runtime_properties(
            name: str,
            payload: DynamicPropertiesRequest,
            scope: str = Query(...),
        ) -> dict[str, Any]:
            self._validate_runtime_scope(scope)
            try:
                registration = self._require_dynamic().update_properties(
                    name, payload.properties, scope_id=ScopeId(scope)
                )
            except KeyError as exc:
                raise operation_error(exc, status_code=404) from exc
            except (ValueError, RuntimeError) as exc:
                raise operation_error(exc) from exc
            return self._registration_payload(registration)
```

- `DELETE /plugins/runtime/{name}`（行 238-244）替换为：

```python
        @router.delete("/plugins/runtime/{name}")
        def uninstall_plugin(name: str, scope: str = Query(...)) -> dict[str, bool]:
            self._validate_runtime_scope(scope)
            try:
                self._require_dynamic().uninstall(name, scope_id=ScopeId(scope))
            except KeyError as exc:
                raise operation_error(exc, status_code=404) from exc
            except (ValueError, RuntimeError) as exc:
                raise operation_error(exc) from exc
            return {"removed": True}
```

- `POST /plugins/runtime/{name}/upgrade`（行 246-252）替换为：

```python
        @router.post("/plugins/runtime/{name}/upgrade")
        def upgrade_plugin(name: str, scope: str = Query(...)) -> dict[str, Any]:
            self._validate_runtime_scope(scope)
            try:
                registration = self._require_dynamic().upgrade(
                    name, scope_id=ScopeId(scope)
                )
            except KeyError as exc:
                raise operation_error(exc, status_code=404) from exc
            except (ValueError, RuntimeError) as exc:
                raise operation_error(exc) from exc
            return self._registration_payload(registration)
```

- `_validate_scope`（行 312-322）之后新增：

```python
    def _validate_runtime_scope(self, scope: str) -> None:
        if scope in KNOWN_RUNTIME_SCOPES:
            return
        if scope.startswith("agent:") and len(scope) > len("agent:"):
            return
        raise http_error(
            400,
            f"Unknown runtime scope: {scope}",
            code="VALIDATION_ERROR",
            error_type="ValidationError",
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_plugin_config_routes.py -q`
Expected: PASS

- [ ] **Step 5: 类型检查**

Run: `python -m mypy src/langharness_api`
Expected: 无错误

- [ ] **Step 6: 提交**

```bash
git add src/langharness_api/plugins/routes/plugins.py tests/test_plugin_config_routes.py
git commit -m "feat: require scope on runtime mutation endpoints"
```

---

### Task 3: 非交互 CLI 强制 scope

**Files:**
- Modify: `src/langharness_cli/plugins/commands/plugins.py:22-23, 26-31, 82-136`
- Test: `tests/test_plugin_commands.py:143-236`（修复基线失败 + 新用例）

**Interfaces:**
- Consumes: 无（本任务新增模块级 helper）
- Produces:
  - 模块级函数 `_is_config_scope(value: str) -> bool`（`api`/`cli`/`agent:*`）
  - 模块级函数 `_is_runtime_scope(value: str) -> bool`（`root`/`server`/`ui`/`agent`/`agent:*`）
  - 非交互所有变更操作：缺 scope 或格式非法 → `ValueError`（信息含 `requires ... --scope root|server|ui|agent|agent:<id>`），退出码 1
  - 非交互 `list --scope` / `config --scope` 传了非法 scope 也报 `ValueError`

- [ ] **Step 1: 修复基线失败用例并新增失败用例**

`tests/test_plugin_commands.py`：

- `test_noninteractive_enable_disable_upgrade_uninstall`（行 183-222）替换为：

```python
def test_noninteractive_enable_disable_upgrade_uninstall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code, calls = run_command(
        monkeypatch,
        ["enable", "api-rate-limit", "--scope", "server"],
        methods={"put": {"enabled": True}},
    )
    assert code == 0
    assert calls[0] == (
        "put",
        "http://127.0.0.1:11534/plugins/runtime/api-rate-limit/enabled",
        {
            "json": {"enabled": True},
            "headers": {"Authorization": "Bearer secret"},
            "timeout": 10.0,
            "params": {"scope": "server"},
        },
    )

    code, calls = run_command(
        monkeypatch,
        ["disable", "api-rate-limit", "--scope", "server"],
        methods={"put": {"enabled": False}},
    )
    assert code == 0
    assert calls[0][2]["json"] == {"enabled": False}
    assert calls[0][2]["params"] == {"scope": "server"}

    code, calls = run_command(
        monkeypatch,
        ["upgrade", "api-rate-limit", "--scope", "server"],
        methods={"post": {"status": "upgraded"}},
    )
    assert code == 0
    assert calls[0][0] == "post"
    assert calls[0][1].endswith("/plugins/runtime/api-rate-limit/upgrade")
    assert calls[0][2]["params"] == {"scope": "server"}

    code, calls = run_command(
        monkeypatch,
        ["uninstall", "api-rate-limit", "--scope", "server"],
        methods={"delete": {"removed": True}},
    )
    assert code == 0
    assert calls[0][0] == "delete"
    assert calls[0][1].endswith("/plugins/runtime/api-rate-limit")
    assert calls[0][2]["params"] == {"scope": "server"}
```

- `test_plugins_lists_runtime_plugins_for_default_scope` 行 292 的断言改为：

```python
    assert captured["params"] is None
```

- 文件末尾新增用例：

```python
def test_noninteractive_runtime_set_requires_scope(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, calls = run_command(
        monkeypatch,
        ["runtime", "set", "api-rate-limit", "plugin.limit=5"],
        methods={},
    )
    assert code == 1
    assert "runtime requires" in capsys.readouterr().out
    assert calls == []


def test_noninteractive_runtime_set_updates_dynamic_properties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code, calls = run_command(
        monkeypatch,
        ["runtime", "set", "echo", "plugin.value=x", "--scope", "server"],
        methods={"put": {"status": "installed"}},
    )
    assert code == 0
    assert calls[0][0] == "put"
    assert calls[0][1].endswith("/plugins/runtime/echo/properties")
    assert calls[0][2]["params"] == {"scope": "server"}
    assert calls[0][2]["json"] == {"properties": {"plugin.value": "x"}}


def test_noninteractive_mutations_reject_invalid_scope(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for args, message in [
        (["enable", "api-rate-limit", "--scope", "mars"], "enable requires"),
        (["disable", "api-rate-limit", "--scope", "mars"], "disable requires"),
        (["upgrade", "api-rate-limit", "--scope", "mars"], "upgrade requires"),
        (["uninstall", "api-rate-limit", "--scope", "mars"], "uninstall requires"),
        (
            ["runtime", "set", "api-rate-limit", "plugin.limit=5", "--scope", "mars"],
            "runtime requires",
        ),
        (["list", "--scope", "mars"], "list --scope must be"),
        (["config", "--scope", "mars"], "config --scope must be"),
    ]:
        code, _ = run_command(monkeypatch, args, methods={})
        assert code == 1
        assert message in capsys.readouterr().out
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_plugin_commands.py -q`
Expected: `test_noninteractive_enable_disable_upgrade_uninstall` 与 `test_plugins_lists_runtime_plugins_for_default_scope` 之外，新增用例 FAIL（`runtime requires` 消息缺失、非法 scope 未被拒绝）

- [ ] **Step 3: 实现非交互校验**

`src/langharness_cli/plugins/commands/plugins.py`：

- `_coerce`（行 26-31）之后新增模块级 helper 与常量：

```python
CONFIG_SCOPES = ("api", "cli")
RUNTIME_SCOPES = ("root", "server", "ui", "agent")


def _is_config_scope(value: str) -> bool:
    return value in CONFIG_SCOPES or value.startswith("agent:")


def _is_runtime_scope(value: str) -> bool:
    return value in RUNTIME_SCOPES or value.startswith("agent:")
```

- `_command_handler`（行 79-141）的 `list` 分支：

```python
            elif args.action == "list":
                if args.scope and not _is_runtime_scope(args.scope):
                    raise ValueError(
                        "list --scope must be root|server|ui|agent|agent:<id>"
                    )
                params = {"scope": args.scope} if args.scope else None
                payload = self._get_raw(context, "/plugins/runtime", params=params)
```

- `config` 分支：

```python
            elif args.action == "config":
                if args.scope and not _is_config_scope(args.scope):
                    raise ValueError("config --scope must be api|cli|agent:<id>")
                payload = self._get_raw(
                    context,
                    "/plugins",
                    params={"scope": args.scope} if args.scope else None,
                )
```

- `runtime` 分支：

```python
            elif args.action == "runtime":
                if (
                    len(args.values) < 3
                    or args.values[0] != "set"
                    or not _is_runtime_scope(args.scope or "")
                ):
                    raise ValueError(
                        "runtime requires set PLUGIN_NAME KEY=VALUE "
                        "--scope root|server|ui|agent|agent:<id>"
                    )
                properties = self._properties(args.values[2:])
```

- `enable`/`disable` 分支：

```python
            elif args.action in {"enable", "disable"}:
                if len(args.values) != 1 or not _is_runtime_scope(args.scope or ""):
                    raise ValueError(
                        f"{args.action} requires PLUGIN_NAME "
                        "--scope root|server|ui|agent|agent:<id>"
                    )
```

- `upgrade` 分支：

```python
            elif args.action == "upgrade":
                if len(args.values) != 1 or not _is_runtime_scope(args.scope or ""):
                    raise ValueError(
                        "upgrade requires PLUGIN_NAME "
                        "--scope root|server|ui|agent|agent:<id>"
                    )
```

- `else`（uninstall）分支：

```python
            else:
                if len(args.values) != 1 or not _is_runtime_scope(args.scope or ""):
                    raise ValueError(
                        "uninstall requires PLUGIN_NAME "
                        "--scope root|server|ui|agent|agent:<id>"
                    )
```

- `install` 分支保持现状（只查 scope 存在性）。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_plugin_commands.py -q`
Expected: 全部 PASS（含修复后的 `test_noninteractive_enable_disable_upgrade_uninstall` 与 `test_plugins_lists_runtime_plugins_for_default_scope`）

- [ ] **Step 5: 提交**

```bash
git add src/langharness_cli/plugins/commands/plugins.py tests/test_plugin_commands.py
git commit -m "feat: enforce scope on non-interactive plugin mutations"
```

---

### Task 4: 交互式 CLI 强制 scope + 清理死代码

**Files:**
- Modify: `src/langharness_cli/plugins/commands/plugins.py:22-23, 237-256, 302-397, 526-550`
- Test: `tests/test_plugin_commands.py:533-656`

**Interfaces:**
- Consumes: Task 3 的 `_is_config_scope` / `_is_runtime_scope`
- Produces:
  - 交互式 `enable|disable` / `uninstall` / `runtime set` 校验 scope 格式，非法打印 `Scope is required. Specify root, server, ui, agent, or agent:<id>.` + usage
  - 交互式 `set` / `config enable|disable` / `history` / `rollback` 校验 config scope，非法打印 `Scope is required. Specify api, cli, or agent:<id>.` + usage
  - `rollback` 新语法：`rollback <config_scope> <version>`
  - 删除：`DEFAULT_CONFIG_SCOPE`、`DEFAULT_RUNTIME_SCOPE` 常量与 `_scope`、`_runtime_scope`、`_is_scope` 方法；`_plugin_arguments` 去掉缺省分支

- [ ] **Step 1: 更新/新增失败用例**

`tests/test_plugin_commands.py`：

- `test_plugins_rollback_uses_default_scope_for_bare_version`（行 626-637）替换为：

```python
def test_plugins_rollback_requires_scope(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> Response:
        calls.append(kwargs)
        return Response(APPLY_RESULT)

    monkeypatch.setattr(httpx, "post", fake_post)
    assert handler_for("plugins")(Context(), "rollback 2") is False
    assert calls == []
    output = capsys.readouterr().out
    assert "Scope is required" in output
    assert "usage" in output.lower()
```

- 文件末尾新增用例：

```python
def test_plugins_history_requires_scope(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_get(url: str, **kwargs: Any) -> Response:
        calls.append((url, kwargs))
        return Response(HISTORY)

    monkeypatch.setattr(httpx, "get", fake_get)
    assert handler_for("plugins")(Context(), "history") is False
    assert calls == []
    output = capsys.readouterr().out
    assert "Scope is required" in output


def test_plugins_history_rejects_unknown_scope(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(httpx, "get", lambda *a, **k: Response(HISTORY))
    assert handler_for("plugins")(Context(), "history mars") is False
    output = capsys.readouterr().out
    assert "Scope is required" in output
    assert "usage" in output.lower()


def test_plugins_runtime_operations_require_valid_scope(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    put_calls: list[tuple[str, dict[str, Any]]] = []
    delete_calls: list[tuple[str, dict[str, Any]]] = []

    def fake_put(url: str, **kwargs: Any) -> Response:
        put_calls.append((url, kwargs))
        return Response({"status": "installed"})

    def fake_delete(url: str, **kwargs: Any) -> Response:
        delete_calls.append((url, kwargs))
        return Response({"removed": True})

    monkeypatch.setattr(httpx, "put", fake_put)
    monkeypatch.setattr(httpx, "delete", fake_delete)
    for line in (
        "enable mars echo",
        "disable mars echo",
        "uninstall mars echo",
        "runtime set mars echo plugin.value=1",
        "enable echo",
    ):
        assert handler_for("plugins")(Context(), line) is False
        assert put_calls == []
        assert delete_calls == []
        assert "Scope is required" in capsys.readouterr().out
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_plugin_commands.py -q`
Expected: 新用例 FAIL（`rollback 2` 仍走 api 缺省、`history` 仍走 api 缺省、`enable mars echo` 仍发请求）

- [ ] **Step 3: 实现交互式校验**

`src/langharness_cli/plugins/commands/plugins.py`：

- 删除行 22-23 两个常量：

```python
DEFAULT_CONFIG_SCOPE = "api"
DEFAULT_RUNTIME_SCOPE = "server"
```

- `_runtime`（行 237-256）开头校验替换为：

```python
    def _runtime(self, context: InteractiveCommandContext, arguments: list[str]) -> None:
        """Update properties of an installed runtime plugin instance."""
        if (
            len(arguments) < 4
            or arguments[0] != "set"
            or not _is_runtime_scope(arguments[1])
        ):
            print("Scope is required. Specify root, server, ui, agent, or agent:<id>.")
            self._usage()
            return
        scope, name = arguments[1], arguments[2]
```

- `_set_runtime_enabled`（行 302-315）开头替换为：

```python
    def _set_runtime_enabled(
        self, context: InteractiveCommandContext, action: str, arguments: list[str]
    ) -> None:
        if len(arguments) != 2 or not _is_runtime_scope(arguments[0]):
            print("Scope is required. Specify root, server, ui, agent, or agent:<id>.")
            self._usage()
            return
        scope, name = arguments
```

- `_uninstall`（行 317-326）开头替换为：

```python
    def _uninstall(
        self, context: InteractiveCommandContext, arguments: list[str]
    ) -> None:
        if len(arguments) != 2 or not _is_runtime_scope(arguments[0]):
            print("Scope is required. Specify root, server, ui, agent, or agent:<id>.")
            self._usage()
            return
        payload = self._delete_raw(
            context, f"/plugins/runtime/{arguments[1]}", params={"scope": arguments[0]}
        )
```

- `_update`（行 328-333）守卫替换为：

```python
        if not arguments or not _is_config_scope(arguments[0]):
            print("Scope is required. Specify api, cli, or agent:<id>.")
            return
```

- `_history`（行 363-375）替换为：

```python
    def _history(
        self, context: InteractiveCommandContext, arguments: list[str]
    ) -> None:
        if not arguments or not _is_config_scope(arguments[0]):
            print("Scope is required. Specify api, cli, or agent:<id>.")
            self._usage()
            return
        scope = arguments[0]
        payload = self._get(context, "/plugins/history", scope=scope)
        self._table(
            f"Configuration history · {scope}",
            ("Version", "Action", "Actor", "Target version"),
            (
                (entry.get("seq"), entry.get("action"), entry.get("actor"), entry.get("target_seq", "-"))
                for entry in payload.get("history") or []
            ),
        )
```

- `_rollback`（行 377-397）替换为：

```python
    def _rollback(
        self, context: InteractiveCommandContext, arguments: list[str]
    ) -> None:
        if len(arguments) != 2 or not _is_config_scope(arguments[0]):
            print("Scope is required. Specify api, cli, or agent:<id>.")
            self._usage()
            return
        scope, version_text = arguments
        try:
            version = int(version_text)
        except ValueError:
            self._usage()
            return
        payload = self._post(
            context, "/plugins/rollback", {"seq": version, "actor": "cli"}, scope=scope
        )
        self._apply(payload)
```

- 删除 `_scope`（行 526-529）、`_runtime_scope`（行 531-535）、`_is_scope`（行 548-550）三个方法。

- `_plugin_arguments`（行 537-546）替换为：

```python
    def _plugin_arguments(
        self, arguments: list[str]
    ) -> tuple[str, str | None, list[str]]:
        if len(arguments) < 2:
            return arguments[0], None, []
        return arguments[0], arguments[1], arguments[2:]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_plugin_commands.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 确认死代码清除**

Run: `grep -rn "DEFAULT_CONFIG_SCOPE\|DEFAULT_RUNTIME_SCOPE\|_runtime_scope\|_is_scope\b" src/langharness_cli/plugins/commands/plugins.py`
Expected: 无输出

- [ ] **Step 6: 提交**

```bash
git add src/langharness_cli/plugins/commands/plugins.py tests/test_plugin_commands.py
git commit -m "feat: enforce scope on interactive plugin mutations"
```

---

### Task 5: 聚合 list 展示 Scope 列

**Files:**
- Modify: `src/langharness_cli/plugins/commands/plugins.py:208-217, 419-433, 497-514`
- Test: `tests/test_plugin_commands.py:258-292, 143-167`

**Interfaces:**
- Consumes: 无
- Produces: `_runtime_table(scope: str | None, plugins)` —— `scope is None` 时标题 `Runtime plugins · all scopes`、首列 `Scope`（取 `entry["scope_id"]`）；单 scope 视图不变

- [ ] **Step 1: 更新失败用例**

`tests/test_plugin_commands.py`：

- `test_plugins_lists_runtime_plugins_for_default_scope`（行 258-292）整体替换为：

```python
def test_plugins_lists_runtime_plugins_across_all_scopes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: dict[str, Any] = {}

    def fake_get(url: str, **kwargs: Any) -> Response:
        captured["url"] = url
        captured.update(kwargs)
        return Response(
            {
                "plugins": [
                    {
                        "name": "api-server",
                        "package_id": "builtin.api",
                        "contribution_id": "server",
                        "version": "1.0.0",
                        "scope_id": "agent:a",
                        "enabled": True,
                        "status": "installed",
                        "specification": "api.server",
                    },
                    {
                        "name": "api-web",
                        "package_id": "builtin.api",
                        "contribution_id": "ui",
                        "version": "1.0.0",
                        "scope_id": "ui",
                        "enabled": True,
                        "status": "installed",
                        "specification": "api.server",
                    },
                ]
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    assert handler_for("plugins")(Context(), "list") is False

    output = capsys.readouterr().out
    assert "Runtime plugins · all scopes" in output
    assert "Scope" in output
    assert "api-server" in output
    assert "agent:a" in output
    assert "api-web" in output
    assert "builtin.api/server" in output
    assert captured["url"].endswith("/plugins/runtime")
    assert captured["params"] is None
```

- 文件末尾新增用例：

```python
def test_plugins_lists_runtime_plugins_for_a_scope_without_scope_column(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_get(url: str, **kwargs: Any) -> Response:
        return Response(
            {
                "plugins": [
                    {
                        "name": "api-server",
                        "package_id": "builtin.api",
                        "contribution_id": "server",
                        "version": "1.0.0",
                        "scope_id": "server",
                        "enabled": True,
                        "status": "installed",
                        "specification": "api.server",
                    }
                ]
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    assert handler_for("plugins")(Context(), "list server") is False

    output = capsys.readouterr().out
    assert "Runtime plugins · scope server" in output
    assert "Scope" not in output


def test_noninteractive_list_without_scope_renders_scope_column(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, calls = run_command(
        monkeypatch,
        ["list"],
        methods={
            "get": {
                "plugins": [
                    {
                        "name": "api-server",
                        "package_id": "builtin.api",
                        "contribution_id": "server",
                        "version": "1.0.0",
                        "scope_id": "agent:a",
                        "enabled": True,
                        "status": "installed",
                        "specification": "api.server",
                    }
                ]
            }
        },
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "Runtime plugins · all scopes" in output
    assert "agent:a" in output
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_plugin_commands.py -q`
Expected: 三个用例 FAIL（标题仍为 `scope all`、无 Scope 列）

- [ ] **Step 3: 实现 Scope 列**

`src/langharness_cli/plugins/commands/plugins.py`：

- `_runtime_table`（行 419-433）替换为：

```python
    def _runtime_table(
        self, scope: str | None, plugins: list[dict[str, Any]]
    ) -> None:
        def row(entry: dict[str, Any]) -> tuple[str, ...]:
            base = (
                entry.get("name", "-"),
                "enabled" if entry.get("enabled", True) else "disabled",
                entry.get("status", "-"),
                f"{entry.get('package_id', '-')}/{entry.get('contribution_id', '-')}",
                entry.get("specification", "-"),
            )
            if scope is None:
                return (str(entry.get("scope_id", "-")), *base)
            return base

        self._table(
            f"Runtime plugins · {'all scopes' if scope is None else f'scope {scope}'}",
            (
                "Scope", "Name", "State", "Status",
                "Package / contribution", "Specification",
            )
            if scope is None
            else (
                "Name", "State", "Status",
                "Package / contribution", "Specification",
            ),
            (row(entry) for entry in sorted(plugins, key=lambda item: str(item.get("name", "")))),
        )
```

- `_list`（行 208-217）中两处调用与空提示改传 `scope` 原值：

```python
    def _list(self, context: InteractiveCommandContext, arguments: list[str]) -> None:
        scope = arguments[0] if arguments else None
        payload = self._get_raw(
            context, "/plugins/runtime", params={"scope": scope} if scope else None
        )
        plugins = payload.get("plugins") or []
        if not plugins:
            print(f"runtime scope {scope or 'all scopes'}: no registered plugins")
            return
        self._runtime_table(scope, plugins)
```

- `_render_noninteractive_result`（行 497-514）中 list 分支：

```python
        if action == "list":
            plugins = payload.get("plugins") or []
            if plugins:
                self._runtime_table(scope, plugins)
            else:
                print(f"runtime scope {scope or 'all scopes'}: no registered plugins")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_plugin_commands.py -q`
Expected: 全部 PASS（基线两个失败至此全部修复）

- [ ] **Step 5: 提交**

```bash
git add src/langharness_cli/plugins/commands/plugins.py tests/test_plugin_commands.py
git commit -m "feat: show scope column when listing runtime plugins across scopes"
```

---

### Task 6: 全量验证与收尾

**Files:**
- 无新改动；仅验证与可能的小修正

**Interfaces:**
- Consumes: Task 1-5 全部产物
- Produces: 全绿测试套件

- [ ] **Step 1: 全量测试**

Run: `python -m pytest tests/ -q`
Expected: 全部 PASS。若有其他文件失败（如 `test_contracts.py`、`test_contract_enforcement.py`、`test_agent_scoping.py`、`test_cli_real_flow.py`），逐个修复并保持 `git add` 精确路径。

- [ ] **Step 2: lint 与类型检查**

Run: `python -m ruff check src tests`
Expected: 无错误

Run: `python -m mypy src`
Expected: 无错误（strict）

- [ ] **Step 3: 残留引用扫描**

Run: `grep -rn "DEFAULT_CONFIG_SCOPE\|DEFAULT_RUNTIME_SCOPE\|_runtime_scope\|set_enabled(\|update_properties(\|\.upgrade(\|\.uninstall(" src --include="*.py" | grep -v "def set_enabled\|def update_properties\|def upgrade\|def uninstall"`
Expected: 仅协调器协议/实现定义与 API 路由的带 `scope_id=` 调用

- [ ] **Step 4: 手动冒烟（可选）**

Run: `python -m langharness --mode server`（另开终端），然后：

```bash
curl -s -X PUT "http://127.0.0.1:11534/plugins/runtime/x/enabled" -H "Authorization: Bearer secret" -H "Content-Type: application/json" -d '{"enabled": true}'
```

Expected: 422（缺 scope）；带 `?scope=server` 时 400/404 之一而非 500。

- [ ] **Step 5: 提交剩余修正**

```bash
git status --short
git add <仅本次涉及的精确路径>
git commit -m "test: full suite green for plugin scope enforcement"
```

- [ ] **Step 6: 收尾核对**

Run: `git log --oneline -8` 与 `git status --short`
Expected: 本次 5-6 个提交在顶部；`.vscode/launch.json` 与 `template_system_prompt.py` 仍为未提交状态（未被本计划提交）。
