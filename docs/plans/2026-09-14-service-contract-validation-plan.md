# 服务契约校验实现计划（类规格迁移 + 双侧签名校验）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 iPOPO 服务在安装与绑定时按 Protocol 契约做运行时签名校验：安装侧违规硬拦（服务不注册），绑定侧违规软隔离（消费方继续运行）。

**Architecture:** 新增 `langharness_plugin/validation.py` 提供 `service_contract` 装饰器（把 Protocol 钉为 Pelix 规格名并登记进 `CONTRACTS`）、调用兼容性校验器（`describe`/`validate`）、`ContractViolationError` 与 `ContractGuard`。各模块 `contracts.py` 的 Protocol 加 pin；组件声明从 `SPEC_X` 字符串改为 Protocol 类；`PluginManager._instantiate` 做安装期硬校验；消费方在 BindField 回调里用 `ContractGuard` 隔离违规 provider。

**Tech Stack:** Python 3.13、Pelix/iPOPO 3.x、pytest、ruff、mypy（strict）、pyright、pytest-cov（95% 门禁）。

**设计文档:** `docs/designs/2026-09-14-service-contract-validation-design.md`

**已验证的前提（不要重复验证，直接依赖）:**
- Pelix/iPOPO 的 `_get_specifications()` 接受类，读 `__SPECIFICATION__` 得到规格名；运行时解析行为与字符串完全一致。
- `__protocol_attrs__` 在类创建时算好：类体内写 `__SPECIFICATION__` 会污染 `isinstance`，**类创建后赋值安全**。
- iPOPO 工厂元数据只留规格字符串，类对象丢失 → 需要 `CONTRACTS` 注册表。
- `ipopo.instantiate()` 返回组件实例；服务在 `@Validate` 之后注册 → 安装期可硬拦。
- `@BindField` 回调异常被 iPOPO 吞掉 → 消费侧只能隔离。
- 现有 25 个 provider/契约配对在「调用兼容性 + 嵌套 Any 通配 + 返回协变」规则下**零违规**，迁移不需要改任何实现签名。
- 只有 `tests/test_plugin_manager_unit.py` 使用 Mock 服务实例；其余测试都用真实插件。
- `examples/plugin_demo` 无测试覆盖、组件无类型注解、其 agent loop 不满足 `AgentLoopProvider`（同步 invoke、无 astream）。计划只做最小改动（Task 13）：contracts 改引用真实核心契约、三个 provider 补注解与 `get_protocol`、agent loop 的 `@Requires*` 用真实协议加守卫；它自身 `@Provides(SPEC_AGENT_LOOP)` 不被任何消费者校验，保持原样。

**计划中的有意取舍（与设计文档一致）:**
- 参数注解仅在 provider 已声明时比对（相等），返回注解必须声明且按协变规则匹配。
- 返回注解允许协变：`dict[str, Any]`（实现）满足 `Mapping[str, Any]`（契约）。
- 未 pin 的规格不校验（第三方自有规格的豁免通道）。

**每个 Task 的最后一步都跑 `make check`（仓库门禁：ruff → mypy → pyright → 干净进程导入 → pytest 覆盖率 95%）。**

---

## Task 1: `service_contract` 装饰器与契约注册表

**Files:**
- Create: `src/langharness_plugin/validation.py`
- Create: `tests/test_validation.py`
- Modify: `tests/test_imports.py`（`PUBLIC_MODULES` 增加 `langharness_plugin.validation`）

- [ ] **Step 1: 写失败测试**

创建 `tests/test_validation.py`：

```python
"""Unit tests for runtime service contract validation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pytest

from langharness_plugin.validation import (
    CONTRACTS,
    contract_for,
    service_contract,
)


@runtime_checkable
@service_contract("test.contract.demo")
class DemoProvider(Protocol):
    def run(self, value: int) -> str: ...


class _Implementation:
    def run(self, value: int) -> str:
        return str(value)


def test_service_contract_pins_and_registers_protocol() -> None:
    assert DemoProvider.__SPECIFICATION__ == "test.contract.demo"
    assert contract_for("test.contract.demo") is DemoProvider
    assert CONTRACTS["test.contract.demo"] is DemoProvider


def test_service_contract_keeps_isinstance_semantics() -> None:
    # 类体内写 __SPECIFICATION__ 会污染 __protocol_attrs__ 并让 isinstance 失效
    assert "__SPECIFICATION__" not in DemoProvider.__protocol_attrs__
    assert isinstance(_Implementation(), DemoProvider)


def test_service_contract_resolves_through_ipopo() -> None:
    from pelix.ipopo.decorators import _get_specifications

    assert _get_specifications(DemoProvider) == ["test.contract.demo"]


def test_unpinned_specification_returns_none() -> None:
    assert contract_for("test.contract.missing") is None


def test_conflicting_pin_raises() -> None:
    class Other(Protocol):
        def run(self, value: int) -> str: ...

    with pytest.raises(ValueError, match="already pinned"):
        service_contract("test.contract.demo")(Other)


def test_repinning_same_class_is_idempotent() -> None:
    assert service_contract("test.contract.demo")(DemoProvider) is DemoProvider
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_validation.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'langharness_plugin.validation'`

- [ ] **Step 3: 写最小实现**

创建 `src/langharness_plugin/validation.py`：

```python
"""Runtime validation of service objects against their Protocol contracts."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

LOGGER = logging.getLogger("langharness.contract")

SPECIFICATION_FIELD = "__SPECIFICATION__"

CONTRACTS: dict[str, type[Any]] = {}


def service_contract(specification: str) -> Callable[[type[Any]], type[Any]]:
    """Pin a Protocol class to a Pelix specification name and register it."""

    def decorate(cls: type[Any]) -> type[Any]:
        existing = CONTRACTS.get(specification)
        if existing is not None and existing is not cls:
            raise ValueError(
                f"specification {specification!r} is already pinned to "
                f"{existing.__name__}"
            )
        setattr(cls, SPECIFICATION_FIELD, specification)
        CONTRACTS[specification] = cls
        return cls

    return decorate


def contract_for(specification: str) -> type[Any] | None:
    """Return the pinned contract for a service specification."""
    return CONTRACTS.get(specification)
```

- [ ] **Step 4: 把新模块加进干净进程导入检查**

在 `tests/test_imports.py` 的 `PUBLIC_MODULES` 里、`"langharness_plugin.plugin_manager",` 之后插入一行：

```python
    "langharness_plugin.validation",
```

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_validation.py tests/test_imports.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
make check
git add src/langharness_plugin/validation.py tests/test_validation.py tests/test_imports.py
git commit -m "新增服务契约 pin 装饰器与运行时契约注册表"
```

---

## Task 2: 契约签名提取 `describe()`

**Files:**
- Modify: `src/langharness_plugin/validation.py`
- Modify: `tests/test_validation.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_validation.py`：

```python
import inspect
from typing import Any, AsyncIterator

from langharness_plugin.validation import describe


class _Shape(Protocol):
    def plain(self, value: int, flag: bool = False) -> str: ...

    def variadic(self, *args: int, **kwargs: str) -> None: ...

    def kw_only(self, *, name: str, count: int = 1) -> None: ...

    def _private(self) -> None: ...


def test_describe_extracts_parameter_shapes() -> None:
    contract = describe(_Shape)
    assert contract.specification is None
    assert contract.name == "_Shape"
    assert [method.name for method in contract.methods] == [
        "kw_only",
        "plain",
        "variadic",
    ]

    plain = contract.methods[1]
    assert [(p.name, p.positional, p.keyword, p.has_default) for p in plain.parameters] == [
        ("value", True, True, False),
        ("flag", True, True, True),
    ]
    assert plain.return_annotation is str
    assert plain.error is None

    variadic = contract.methods[2]
    assert variadic.var_positional is True
    assert variadic.var_keyword is True
    assert variadic.parameters == ()

    kw_only = contract.methods[0]
    assert [(p.name, p.positional, p.keyword) for p in kw_only.parameters] == [
        ("name", False, True),
        ("count", False, True),
    ]


def test_describe_resolves_string_annotations() -> None:
    # tests/*.py 有 from __future__ import annotations，注解在提取时必须已解析
    contract = describe(_Shape)
    plain = contract.methods[1]
    assert plain.parameters[0].annotation is int
    assert plain.parameters[1].annotation is bool


def test_describe_reports_unresolvable_annotation() -> None:
    def broken(self, value: "MissingName") -> None: ...  # noqa: F821

    namespace = {"broken": broken}
    contract_class = type("BrokenProfile", (Protocol,), namespace)

    method = describe(contract_class).methods[0]
    assert method.error is not None
    assert "MissingName" in method.error


def test_describe_caches_result() -> None:
    assert describe(_Shape) is describe(_Shape)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_validation.py -q`
Expected: FAIL — `ImportError: cannot import name 'describe'`

- [ ] **Step 3: 写实现**

在 `src/langharness_plugin/validation.py` 扩展：把顶部 import 补成

```python
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, get_type_hints
```

在 `contract_for` 之后加入（`Violation` 等类型在后续 Task 加入，本 Task 只加契约描述类型）：

```python
@dataclass(frozen=True)
class ParameterContract:
    """One parameter of a contract method."""

    name: str
    positional: bool
    keyword: bool
    has_default: bool
    annotation: Any


@dataclass(frozen=True)
class MethodContract:
    """The callable shape of one contract method."""

    name: str
    parameters: tuple[ParameterContract, ...]
    var_positional: bool
    var_keyword: bool
    return_annotation: Any
    error: str | None = None


@dataclass(frozen=True)
class ProtocolContract:
    """The full expected shape of a service contract."""

    specification: str | None
    name: str
    methods: tuple[MethodContract, ...]


_CONTRACT_CACHE: dict[type[Any], ProtocolContract] = {}


def _resolve_hints(member: Callable[..., Any]) -> tuple[dict[str, Any], str | None]:
    try:
        return get_type_hints(member), None
    except Exception as exc:
        # 前向引用断裂等注解解析失败不能中断校验，记录原因交给 validate 报告
        return {}, f"{type(exc).__name__}: {exc}"


def _method_contract(name: str, member: Callable[..., Any]) -> MethodContract:
    try:
        signature = inspect.signature(member)
    except (TypeError, ValueError) as exc:
        return MethodContract(
            name=name,
            parameters=(),
            var_positional=False,
            var_keyword=False,
            return_annotation=None,
            error=f"{type(exc).__name__}: {exc}",
        )
    hints, error = _resolve_hints(member)
    parameters: list[ParameterContract] = []
    var_positional = False
    var_keyword = False
    for parameter in signature.parameters.values():
        if parameter.name in {"self", "cls"}:
            continue
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            var_positional = True
        elif parameter.kind is inspect.Parameter.VAR_KEYWORD:
            var_keyword = True
        else:
            parameters.append(
                ParameterContract(
                    name=parameter.name,
                    positional=parameter.kind
                    in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    ),
                    keyword=parameter.kind
                    in (
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        inspect.Parameter.KEYWORD_ONLY,
                    ),
                    has_default=parameter.default is not inspect.Parameter.empty,
                    annotation=hints.get(parameter.name),
                )
            )
    return MethodContract(
        name=name,
        parameters=tuple(parameters),
        var_positional=var_positional,
        var_keyword=var_keyword,
        return_annotation=hints.get("return"),
        error=error,
    )


def describe(protocol: type[Any]) -> ProtocolContract:
    """Return the cached expected shape of a pinned service contract."""
    cached = _CONTRACT_CACHE.get(protocol)
    if cached is not None:
        return cached
    methods = tuple(
        _method_contract(name, member)
        for name, member in inspect.getmembers(protocol, inspect.isfunction)
        if not name.startswith("_")
    )
    specification = getattr(protocol, SPECIFICATION_FIELD, None)
    contract = ProtocolContract(
        specification=specification if isinstance(specification, str) else None,
        name=protocol.__name__,
        methods=methods,
    )
    _CONTRACT_CACHE[protocol] = contract
    return contract
```

注意：`_Shape` 的方法按 `inspect.getmembers` 的字母序返回（`kw_only`, `plain`, `variadic`），测试断言依赖这个顺序。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_validation.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
make check
git add src/langharness_plugin/validation.py tests/test_validation.py
git commit -m "契约签名提取：describe 剥离 self、区分参数种类、解析字符串注解"
```

---

## Task 3: 注解兼容判定（Any 通配、union 归一、返回协变）

> **执行期修正（2026-09-14 实现后回填）**：本节的示例代码在两轮代码审查后被修正了三处，
> 重跑本节时以仓库当前代码为准：
> 1) `isinstance(expected_args, list)` 分支是死代码（`get_args` 恒返回 tuple），导致
>    `Callable[[Any], str]` 里的 `Any` 通配失效 → 改为在 `_annotations_match` 顶部加
>    「任一侧是 list 即逐项比对」规则；
> 2) union 判定必须放在 origin-None 早退**之前**，且**任一侧**为 union 即进入（另一侧
>    视为单分支），否则契约 `str | None` 会误拒实现 `str`；
> 3) 返回位置的 union 按**协变**方向判定（actual 的每个分支要被 expected 覆盖），参数位置
>    保持反协变方向（expected 的每个分支要被 actual 覆盖）；返回位置的普通类按
>    `issubclass` 容忍子类。

**Files:**
- Modify: `src/langharness_plugin/validation.py`
- Modify: `tests/test_validation.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_validation.py`：

```python
from collections.abc import Callable, Mapping
from langharness_plugin.validation import validate


class _NestedAny(Protocol):
    def run(self, value: "list[Any]") -> "list[Any]": ...


def test_any_is_a_wildcard_at_every_depth() -> None:
    class Concrete:
        def run(self, value: list[object]) -> list[str]:
            return []

    assert validate(Concrete(), _NestedAny) == ()


def test_optional_matches_union_spelling() -> None:
    from typing import Optional

    class Expected(Protocol):
        def run(self) -> "int | None": ...

    class Concrete:
        def run(self) -> Optional[int]:
            return None

    assert validate(Concrete(), Expected) == ()


def test_return_annotation_allows_covariance() -> None:
    class Expected(Protocol):
        def run(self) -> "Mapping[str, Any]": ...

    class Concrete:
        def run(self) -> dict[str, Any]:
            return {}

    assert validate(Concrete(), Expected) == ()


def test_mismatched_return_annotation_is_reported() -> None:
    class Expected(Protocol):
        def run(self) -> "list[str]": ...

    class Concrete:
        def run(self) -> list[int]:
            return []

    codes = [violation.code for violation in validate(Concrete(), Expected)]
    assert codes == ["RETURN_ANNOTATION_MISMATCH"]


def test_parameter_annotation_mismatch_is_reported() -> None:
    class Expected(Protocol):
        def run(self, value: int) -> None: ...

    class Concrete:
        def run(self, value: str) -> None: ...

    codes = [violation.code for violation in validate(Concrete(), Expected)]
    assert codes == ["PARAM_ANNOTATION_MISMATCH"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_validation.py -q`
Expected: FAIL — `ImportError: cannot import name 'validate'`

- [ ] **Step 3: 写实现**

在 `src/langharness_plugin/validation.py` 中 `describe` 之前加入：

```python
def _origin(annotation: Any) -> Any:
    origin = get_origin(annotation)
    return typing.Union if origin is types.UnionType else origin


def _annotations_match(expected: Any, actual: Any, *, covariance: bool = False) -> bool:
    """Check an actual annotation against the expected one.

    ``Any`` matches anything at every depth; unions compare arm-wise and
    ``X | None`` equals ``Optional[X]``; with ``covariance`` a more specific
    origin is accepted (``dict`` satisfies ``Mapping``).
    """
    if expected is Any or expected is None:
        return True
    if actual is Any or actual is None:
        return True
    if expected == actual:
        return True
    expected_origin = _origin(expected)
    actual_origin = _origin(actual)
    expected_args = get_args(expected)
    actual_args = get_args(actual)
    if isinstance(expected_args, list) and isinstance(actual_args, list):
        # Callable 的参数列表是普通 list：逐项比对
        return len(expected_args) == len(actual_args) and all(
            _annotations_match(item, other, covariance=covariance)
            for item, other in zip(expected_args, actual_args)
        )
    if expected_origin is None or actual_origin is None:
        return False
    if expected_origin is typing.Union and actual_origin is typing.Union:
        return all(
            any(
                _annotations_match(arm, other, covariance=covariance)
                for other in actual_args
            )
            for arm in expected_args
        )
    if expected_origin is not actual_origin:
        if not (
            covariance
            and isinstance(expected_origin, type)
            and isinstance(actual_origin, type)
        ):
            return False
        try:
            if not issubclass(actual_origin, expected_origin):
                return False
        except TypeError:
            return False
    if not expected_args or not actual_args:
        return True
    if len(expected_args) != len(actual_args):
        return False
    return all(
        _annotations_match(item, other, covariance=covariance)
        for item, other in zip(expected_args, actual_args)
    )
```

并把顶部 import 补成：

```python
import inspect
import logging
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, get_args, get_origin, get_type_hints
```

在文件末尾先加入最小 `validate`（本 Task 只覆盖注解检查；方法存在性与参数形状检查在 Task 4 补齐）：

```python
def validate(instance: Any, protocol: type[Any]) -> tuple[Violation, ...]:
    """Check an instance against a pinned contract and return all violations."""
    contract = describe(protocol)
    specification = contract.specification or contract.name
    violations: list[Violation] = []
    for expected in contract.methods:
        if expected.error is not None:
            violations.append(
                Violation(specification, contract.name, expected.name,
                          "UNRESOLVED_SIGNATURE", expected.error)
            )
            continue
        member = getattr(instance, expected.name, None)
        actual = _method_contract(expected.name, member)
        if expected.return_annotation is not None and expected.return_annotation is not Any:
            if actual.return_annotation is None:
                violations.append(
                    Violation(specification, contract.name, expected.name,
                              "RETURN_ANNOTATION_MISSING",
                              f"expected {expected.return_annotation!r}")
                )
            elif not _annotations_match(
                expected.return_annotation, actual.return_annotation, covariance=True
            ):
                violations.append(
                    Violation(specification, contract.name, expected.name,
                              "RETURN_ANNOTATION_MISMATCH",
                              f"{actual.return_annotation!r} does not satisfy "
                              f"{expected.return_annotation!r}")
                )
        by_name = {parameter.name: parameter for parameter in actual.parameters}
        for parameter in expected.parameters:
            actual_parameter = by_name.get(parameter.name)
            if actual_parameter is None or parameter.annotation is None:
                continue
            if not _annotations_match(parameter.annotation, actual_parameter.annotation):
                violations.append(
                    Violation(specification, contract.name, expected.name,
                              "PARAM_ANNOTATION_MISMATCH",
                              f"parameter {parameter.name!r} is "
                              f"{actual_parameter.annotation!r}, expected "
                              f"{parameter.annotation!r}")
                )
    return tuple(violations)
```

并在 `contract_for` 之后补 `Violation` 类型：

```python
from typing import Literal

ViolationCode = Literal[
    "MISSING_METHOD",
    "NOT_CALLABLE",
    "PARAM_NOT_ACCEPTED",
    "PARAM_KIND_CONFLICT",
    "PARAM_EXTRA_REQUIRED",
    "PARAM_ANNOTATION_MISMATCH",
    "RETURN_ANNOTATION_MISSING",
    "RETURN_ANNOTATION_MISMATCH",
    "UNRESOLVED_SIGNATURE",
]


@dataclass(frozen=True)
class Violation:
    """One failed contract check."""

    specification: str
    protocol: str
    method: str
    code: ViolationCode
    detail: str
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_validation.py -q`
Expected: PASS（`_NestedAny` 等测试里未实现方法的场景此时不会触发 MISSING_METHOD，因为那是 Task 4 的内容；本 Task 的测试都提供了方法）

- [ ] **Step 5: 提交**

```bash
make check
git add src/langharness_plugin/validation.py tests/test_validation.py
git commit -m "注解兼容判定：Any 全深度通配、union 归一、返回注解允许协变"
```

---

## Task 4: 方法存在性与参数形状校验

> **执行期修正（2026-09-14 实现后回填）**：`_parameter_problems` 的 `PARAM_EXTRA_REQUIRED`
> 判定改为位置感知——实现侧未与契约同名的必填参数，若落在契约位置参数的前缀内，视为被位置填充，
> 不再报 extra-required。否则本节的 `test_unaccepted_parameter_is_reported`（改名参数只应得到
> `PARAM_NOT_ACCEPTED`）与本节代码片段自相矛盾。已知窄边界：契约 `run(value)` vs 实现
> `run(force, value)` 会漏报（实际上不存在合规调用）；彻底解决需改用
> `inspect.Signature.bind` 模拟调用，列为后续可选优化。

**Files:**
- Modify: `src/langharness_plugin/validation.py`
- Modify: `tests/test_validation.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_validation.py`：

```python
class _Tool(Protocol):
    def get_tools(self) -> "list[Any]": ...

    def get_plugin_info(self) -> "dict[str, str]": ...


def _codes(instance: Any, protocol: type[Any] = _Tool) -> list[str]:
    return [violation.code for violation in validate(instance, protocol)]


def test_missing_method_is_reported() -> None:
    class Partial:
        def get_tools(self) -> list[Any]:
            return []

    assert _codes(Partial()) == ["MISSING_METHOD"]


def test_not_callable_member_is_reported() -> None:
    class NotCallable:
        get_tools = "nope"

        def get_plugin_info(self) -> dict[str, str]:
            return {}

    assert _codes(NotCallable()) == ["NOT_CALLABLE"]


def test_keyword_only_parameter_is_accepted_by_var_keyword() -> None:
    class Expected(Protocol):
        def run(self, *, name: str) -> None: ...

    class Concrete:
        def run(self, **kwargs: str) -> None: ...

    assert _codes(Concrete(), Expected) == []


def test_positional_parameter_is_accepted_by_var_positional() -> None:
    class Expected(Protocol):
        def run(self, value: int) -> None: ...

    class Concrete:
        def run(self, *args: int) -> None: ...

    assert _codes(Concrete(), Expected) == []


def test_unaccepted_parameter_is_reported() -> None:
    class Expected(Protocol):
        def run(self, value: int) -> None: ...

    class Concrete:
        def run(self, other: int) -> None: ...

    assert _codes(Concrete(), Expected) == ["PARAM_NOT_ACCEPTED"]


def test_kind_conflict_is_reported() -> None:
    class Expected(Protocol):
        def run(self, value: int) -> None: ...

    class Concrete:
        def run(self, *, value: int) -> None: ...

    assert _codes(Concrete(), Expected) == ["PARAM_KIND_CONFLICT"]


def test_extra_required_parameter_is_reported() -> None:
    class Concrete:
        def get_tools(self) -> list[Any]:
            return []

        def get_plugin_info(self) -> dict[str, str]:
            return {}

        def reload(self, root: str) -> None: ...

    class Expected(Protocol):
        def reload(self) -> None: ...

    assert _codes(Concrete(), Expected) == ["PARAM_EXTRA_REQUIRED"]


def test_extra_parameter_with_default_is_tolerated() -> None:
    class Concrete:
        def get_tools(self) -> list[Any]:
            return []

        def get_plugin_info(self) -> dict[str, str]:
            return {}

        def reload(self, root: str = ".") -> None: ...

    class Expected(Protocol):
        def reload(self) -> None: ...

    assert _codes(Concrete(), Expected) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_validation.py -q`
Expected: FAIL — 缺失方法场景得到 `[]`（应为 `MISSING_METHOD`），其余形状用例同样失败

- [ ] **Step 3: 写实现**

在 `validate` 之前加入参数形状检查，并改写 `validate` 主体：

```python
def _parameter_problems(
    expected: MethodContract, actual: MethodContract
) -> list[tuple[ViolationCode, str]]:
    problems: list[tuple[ViolationCode, str]] = []
    by_name = {parameter.name: parameter for parameter in actual.parameters}
    for parameter in expected.parameters:
        match = by_name.get(parameter.name)
        if match is not None:
            if (parameter.positional and not match.positional) or (
                parameter.keyword and not match.keyword
            ):
                problems.append(
                    (
                        "PARAM_KIND_CONFLICT",
                        f"parameter {parameter.name!r} cannot be passed as "
                        f"{'positional' if parameter.positional and not match.positional else 'keyword'}",
                    )
                )
            continue
        absorbed = (parameter.positional and actual.var_positional) or (
            parameter.keyword and actual.var_keyword
        )
        if not absorbed:
            problems.append(
                (
                    "PARAM_NOT_ACCEPTED",
                    f"parameter {parameter.name!r} is not accepted",
                )
            )
    expected_names = {parameter.name for parameter in expected.parameters}
    for parameter in actual.parameters:
        if parameter.name in expected_names or parameter.has_default:
            continue
        problems.append(
            (
                "PARAM_EXTRA_REQUIRED",
                f"parameter {parameter.name!r} has no default and is not part of the contract",
            )
        )
    return problems
```

`validate` 中「取成员」部分替换为：

```python
        member = getattr(instance, expected.name, None)
        if member is None:
            violations.append(
                Violation(specification, contract.name, expected.name,
                          "MISSING_METHOD",
                          f"{contract.name}.{expected.name} is not implemented")
            )
            continue
        if not callable(member):
            violations.append(
                Violation(specification, contract.name, expected.name,
                          "NOT_CALLABLE",
                          f"{contract.name}.{expected.name} is not callable")
            )
            continue
        actual = _method_contract(expected.name, member)
        if actual.error is not None:
            violations.append(
                Violation(specification, contract.name, expected.name,
                          "UNRESOLVED_SIGNATURE", actual.error)
            )
            continue
        for code, detail in _parameter_problems(expected, actual):
            violations.append(
                Violation(specification, contract.name, expected.name, code, detail)
            )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_validation.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
make check
git add src/langharness_plugin/validation.py tests/test_validation.py
git commit -m "契约校验补齐方法存在性与参数形状判定（含 *args/**kwargs 吸收）"
```

---

## Task 5: `ContractViolationError` 与消息格式

**Files:**
- Modify: `src/langharness_plugin/validation.py`
- Modify: `tests/test_validation.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_validation.py`：

```python
from langharness_plugin.validation import (
    ContractViolationError,
    format_violations,
)


def test_violation_error_message_is_attributable() -> None:
    class Concrete:
        def get_tools(self) -> list[Any]:
            return []

    violations = validate(Concrete(), _Tool)
    error = ContractViolationError(
        plugin="runtime-llm",
        specification="agent.plugin.llm",
        protocol="LLMProvider",
        violations=violations,
    )
    assert error.plugin == "runtime-llm"
    assert error.specification == "agent.plugin.llm"
    assert error.protocol == "LLMProvider"
    assert error.violations == violations
    assert str(error).startswith(
        "plugin 'runtime-llm' violates 'agent.plugin.llm' (LLMProvider): "
    )
    assert "get_plugin_info: MISSING_METHOD" in str(error)


def test_format_violations_joins_entries() -> None:
    class Concrete:
        def get_tools(self) -> list[Any]:
            return []

    rendered = format_violations(validate(Concrete(), _Tool))
    assert rendered == (
        "get_plugin_info: MISSING_METHOD "
        "(_Tool.get_plugin_info is not implemented)"
    )
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_validation.py -q`
Expected: FAIL — `ImportError: cannot import name 'ContractViolationError'`

- [ ] **Step 3: 写实现**

在 `src/langharness_plugin/validation.py` 的 `Violation` 之后加入：

```python
def format_violations(violations: Iterable[Violation]) -> str:
    """Render violations as ``method: CODE (detail)`` entries."""
    return "; ".join(
        f"{violation.method}: {violation.code} ({violation.detail})"
        for violation in violations
    )


class ContractViolationError(RuntimeError):
    """Raised when a service does not conform to its contract."""

    def __init__(
        self,
        plugin: str,
        specification: str,
        protocol: str,
        violations: tuple[Violation, ...],
    ) -> None:
        self.plugin = plugin
        self.specification = specification
        self.protocol = protocol
        self.violations = violations
        super().__init__(
            f"plugin {plugin!r} violates {specification!r} ({protocol}): "
            f"{format_violations(violations)}"
        )
```

顶部 import 增加 `from collections.abc import Callable, Iterable`。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_validation.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
make check
git add src/langharness_plugin/validation.py tests/test_validation.py
git commit -m "新增 ContractViolationError：聚合违规并给出可归因消息"
```

---

## Task 6: `ContractGuard`（消费侧隔离）

**Files:**
- Modify: `src/langharness_plugin/validation.py`
- Modify: `tests/test_validation.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_validation.py`：

```python
import logging

from langharness_plugin.validation import ContractGuard


class _Owner:
    def __init__(self) -> None:
        self._tools: list[Any] = []
        self._best: Any = None


def test_guard_admits_conforming_service() -> None:
    owner = _Owner()
    guard = ContractGuard(owner, "_tools", _Tool)

    class Good:
        def get_tools(self) -> list[Any]:
            return []

        def get_plugin_info(self) -> dict[str, str]:
            return {}

    service = Good()
    assert guard.admit(service) is True
    assert guard.rejected() == {}


def test_guard_quarantines_aggregate_service(caplog: pytest.LogCaptureFixture) -> None:
    owner = _Owner()
    guard = ContractGuard(owner, "_tools", _Tool)

    class Bad:
        def get_plugin_info(self) -> dict[str, str]:
            return {}

    service = Bad()
    owner._tools.append(service)

    with caplog.at_level(logging.ERROR, logger="langharness.contract"):
        assert guard.admit(service) is False

    assert owner._tools == []
    assert "get_tools: MISSING_METHOD" in caplog.text
    assert guard.rejected() == {id(service): validate(service, _Tool)}


def test_guard_quarantines_best_field() -> None:
    owner = _Owner()
    guard = ContractGuard(owner, "_best", _Tool)

    class Bad:
        def get_plugin_info(self) -> dict[str, str]:
            return {}

    service = Bad()
    owner._best = service

    assert guard.admit(service) is False
    assert owner._best is None


def test_guard_release_forgets_service() -> None:
    owner = _Owner()
    guard = ContractGuard(owner, "_tools", _Tool)

    class Bad:
        def get_plugin_info(self) -> dict[str, str]:
            return {}

    service = Bad()
    owner._tools.append(service)
    guard.admit(service)
    assert len(guard.rejected()) == 1

    guard.release(service)
    assert guard.rejected() == {}


def test_guard_quarantine_ignores_unrelated_list_entries() -> None:
    owner = _Owner()
    guard = ContractGuard(owner, "_tools", _Tool)

    class Bad:
        def get_plugin_info(self) -> dict[str, str]:
            return {}

    class Twin:
        def get_plugin_info(self) -> dict[str, str]:
            return {}

        def __eq__(self, other: object) -> bool:  # 服务可能重载 __eq__，隔离必须按身份
            return True

    service = Bad()
    twin = Twin()
    owner._tools.extend([twin, service])
    assert guard.admit(service) is False
    assert owner._tools == [twin]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_validation.py -q`
Expected: FAIL — `ImportError: cannot import name 'ContractGuard'`

- [ ] **Step 3: 写实现**

在 `src/langharness_plugin/validation.py` 末尾加入：

```python
def _quarantine(owner: Any, field: str, service: Any) -> None:
    current = getattr(owner, field, None)
    if isinstance(current, list):
        for index, item in enumerate(current):
            if item is service:
                del current[index]
                break
    elif current is service:
        setattr(owner, field, None)


class ContractGuard:
    """Validates services bound to one component field, quarantining violators."""

    def __init__(self, owner: Any, field: str, protocol: type[Any]) -> None:
        self._owner = owner
        self._field = field
        self._protocol = protocol
        self._rejected: dict[int, tuple[Violation, ...]] = {}

    @property
    def protocol(self) -> type[Any]:
        return self._protocol

    def rejected(self) -> dict[int, tuple[Violation, ...]]:
        """Return quarantined services, keyed by object id."""
        return dict(self._rejected)

    def admit(self, service: Any) -> bool:
        """Return True for conforming services; quarantine and log the rest."""
        violations = validate(service, self._protocol)
        if not violations:
            return True
        self._rejected[id(service)] = violations
        _quarantine(self._owner, self._field, service)
        LOGGER.error(
            "service quarantined from %s (%s): %s",
            self._field,
            describe(self._protocol).name,
            format_violations(violations),
        )
        return False

    def release(self, service: Any) -> None:
        """Forget quarantine bookkeeping for an unbound service."""
        self._rejected.pop(id(service), None)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_validation.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
make check
git add src/langharness_plugin/validation.py tests/test_validation.py
git commit -m "新增 ContractGuard：绑定期校验并按身份隔离违规 provider"
```

---

## Task 7: 安装侧硬拦（PluginManager）

**Files:**
- Modify: `src/langharness_plugin/plugin_manager.py:133-141`
- Create: `tests/test_contract_enforcement.py`
- Modify: `tests/test_plugin_manager_unit.py`（假规格名改到未 pin 的 `test.plugin.*`，避免 Mock 实例被校验）

- [ ] **Step 1: 写失败测试**

创建 `tests/test_contract_enforcement.py`：

```python
"""Contract enforcement tests: install-time rejection and bind-time quarantine."""

from __future__ import annotations

from typing import Any, Protocol
from unittest.mock import Mock

import pytest

from langharness_plugin.plugin_manager import PluginManager
from langharness_plugin.registry import PluginDescriptor, PluginRegistry
from langharness_plugin.validation import (
    ContractViolationError,
    service_contract,
)


@service_contract("test.enforce.tool")
class ToolLike(Protocol):
    def get_tools(self) -> list[Any]: ...


class Conforming:
    def get_tools(self) -> list[Any]:
        return []


class NonConforming:
    def get_tools(self, root: str) -> list[Any]:
        return []


def _descriptor(specification: str) -> PluginDescriptor:
    return PluginDescriptor(
        name="probe",
        version="1.0.0",
        module="module.probe",
        factory="probe-factory",
        instance="probe",
        specification=specification,
    )


def _manager_with_instance(instance: Any) -> PluginManager:
    manager = PluginManager(PluginRegistry())
    manager._framework = Mock()
    manager._context = Mock()
    manager._ipopo = Mock()
    manager._ipopo.instantiate.return_value = instance
    manager._context.install_bundle.return_value = Mock()
    return manager


def test_install_rejects_non_conforming_component() -> None:
    manager = _manager_with_instance(NonConforming())

    with pytest.raises(ContractViolationError) as excinfo:
        manager.install_plugin(_descriptor("test.enforce.tool"))

    assert excinfo.value.plugin == "probe"
    assert "PARAM_NOT_ACCEPTED" in str(excinfo.value)
    manager._ipopo.kill.assert_called_once_with("probe")
    assert "probe" not in manager._bound
    assert manager._ipopo.instantiate.call_count == 1


def test_install_accepts_conforming_component() -> None:
    manager = _manager_with_instance(Conforming())

    manager.install_plugin(_descriptor("test.enforce.tool"))

    assert manager.installed_names() == {"probe"}
    assert "probe" in manager._bound
    manager._ipopo.kill.assert_not_called()


def test_install_skips_unpinned_specification() -> None:
    manager = _manager_with_instance(NonConforming())

    manager.install_plugin(_descriptor("test.enforce.unpinned"))

    assert "probe" in manager._bound
    manager._ipopo.kill.assert_not_called()
```

在 `tests/test_plugin_manager_unit.py` 的 `descriptor()` 助手里把规格名改掉（这些测试用 Mock 实例，不该进入契约校验路径）：

```python
        specification=f"test.plugin.{name}",
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_contract_enforcement.py -q`
Expected: FAIL — `test_install_rejects_non_conforming_component` 不抛异常（当前 `_instantiate` 不校验）

- [ ] **Step 3: 写实现**

`src/langharness_plugin/plugin_manager.py`：

顶部 import 增加：

```python
from langharness_plugin.validation import (
    ContractViolationError,
    contract_for,
    validate,
)
```

`_instantiate` 改为：

```python
    def _instantiate(self, descriptor: PluginDescriptor) -> None:
        if descriptor.name in self._bound:
            raise ValueError(f"Plugin {descriptor.name!r} is already bound")
        instance = self._ipopo.instantiate(
            descriptor.factory,
            descriptor.instance,
            dict(descriptor.properties) or None,
        )
        protocol = contract_for(descriptor.specification)
        if protocol is not None:
            violations = validate(instance, protocol)
            if violations:
                # 违规组件在服务注册表可见前就被击杀，安装方立刻拿到归因错误
                self._ipopo.kill(descriptor.instance)
                raise ContractViolationError(
                    plugin=descriptor.name,
                    specification=descriptor.specification,
                    protocol=protocol.__name__,
                    violations=violations,
                )
        self._bound.add(descriptor.name)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_contract_enforcement.py tests/test_plugin_manager_unit.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
make check
git add src/langharness_plugin/plugin_manager.py tests/test_contract_enforcement.py tests/test_plugin_manager_unit.py
git commit -m "PluginManager 安装期硬校验契约：违规实例击杀且不进入绑定集"
```

---

## Task 8: 核心契约 pin 与 `AgentLoopProvider`

**Files:**
- Modify: `src/langharness_core/contracts.py`
- Modify: `tests/test_contracts.py`

- [ ] **Step 1: 写失败测试**

把 `tests/test_contracts.py` 重写为：

```python
"""Contract tests for plugin service specifications and protocols."""

from __future__ import annotations

from typing import Any

import pytest

from langharness_core import contracts
from langharness_core.plugins.llm.llm import LLMPlugin
from langharness_core.plugins.middleware.template_middleware import (
    TemplateMiddlewarePlugin,
)
from langharness_core.plugins.system_prompt.template_system_prompt import (
    TemplateSystemPromptPlugin,
)
from langharness_core.plugins.tools.tools import ToolPlugin
from langharness_plugin.validation import contract_for, validate

PROTOCOLS = (
    (contracts.SPEC_LLM, contracts.LLMProvider, LLMPlugin),
    (contracts.SPEC_TOOL, contracts.ToolProvider, ToolPlugin),
    (
        contracts.SPEC_MIDDLEWARE,
        contracts.MiddlewareProvider,
        TemplateMiddlewarePlugin,
    ),
    (
        contracts.SPEC_SYSTEM_PROMPT,
        contracts.SystemPromptProvider,
        TemplateSystemPromptPlugin,
    ),
)


@pytest.mark.parametrize(("specification", "protocol", "plugin"), PROTOCOLS)
def test_protocols_are_pinned_to_their_specifications(
    specification: str, protocol: type[Any], plugin: type[Any]
) -> None:
    assert contract_for(specification) is protocol
    assert isinstance(plugin(), protocol)


@pytest.mark.parametrize(
    ("protocol", "plugin"),
    [(protocol, plugin) for _, protocol, plugin in PROTOCOLS],
)
def test_concrete_plugins_conform_to_their_protocols(
    protocol: type[Any], plugin: type[Any]
) -> None:
    assert validate(plugin(), protocol) == ()


def test_pin_does_not_pollute_protocol_members() -> None:
    for _, protocol, _ in PROTOCOLS:
        assert "__SPECIFICATION__" not in protocol.__protocol_attrs__


def test_agent_loop_contract_is_pinned() -> None:
    from langharness_core.plugins.loop.agent_loop import PluginAgentLoop

    assert contract_for(contracts.SPEC_AGENT_LOOP) is contracts.AgentLoopProvider
    assert validate(PluginAgentLoop(), contracts.AgentLoopProvider) == ()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_contracts.py -q`
Expected: FAIL — `contract_for(...)` 返回 None；`AgentLoopProvider` 不存在

- [ ] **Step 3: 写实现**

`src/langharness_core/contracts.py`：

顶部 import 增加：

```python
from collections.abc import AsyncIterator

from langharness_plugin.validation import service_contract
```

给每个 Protocol 加 `@service_contract(SPEC_X)` 装饰器（在 `@runtime_checkable` 之上），pin 值用同文件里已有的常量：

```python
@service_contract(SPEC_LLM)
@runtime_checkable
class LLMProvider(Protocol):
    """Contract implemented by every ``agent.plugin.llm`` service."""
    ...
```

需要 pin 的 15 个协议与常量对应关系：

| Protocol | 常量 |
| --- | --- |
| `LLMProvider` | `SPEC_LLM` |
| `ToolProvider` | `SPEC_TOOL` |
| `MiddlewareProvider` | `SPEC_MIDDLEWARE` |
| `SystemPromptProvider` | `SPEC_SYSTEM_PROMPT` |
| `ResponseFormatProvider` | `SPEC_RESPONSE_FORMAT` |
| `StateSchemaProvider` | `SPEC_STATE_SCHEMA` |
| `ContextSchemaProvider` | `SPEC_CONTEXT_SCHEMA` |
| `CheckpointerProvider` | `SPEC_CHECKPOINTER` |
| `StoreProvider` | `SPEC_STORE` |
| `InterruptBeforeProvider` | `SPEC_INTERRUPT_BEFORE` |
| `InterruptAfterProvider` | `SPEC_INTERRUPT_AFTER` |
| `DebugProvider` | `SPEC_DEBUG` |
| `NameProvider` | `SPEC_NAME` |
| `CacheProvider` | `SPEC_CACHE` |
| `TransformersProvider` | `SPEC_TRANSFORMERS` |

文件末尾新增（`astream` 是异步生成器，按非 async 的 `def ... -> AsyncIterator[...]` 声明才与组件结构兼容）：

```python
@service_contract(SPEC_AGENT_LOOP)
@runtime_checkable
class AgentLoopProvider(Protocol):
    """Contract implemented by every ``agent.loop`` service."""

    def invoke(self, message: str, *, thread_id: str | None = None) -> Any: ...

    def astream(
        self, message: str, *, thread_id: str | None = None
    ) -> AsyncIterator[dict[str, Any]]: ...

    def describe(self) -> dict[str, Any]: ...
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_contracts.py -q`
Expected: PASS（若 `validate(PluginAgentLoop(), AgentLoopProvider)` 报出额外违规，先核对组件签名再调整协议声明，不要放宽规则）

- [ ] **Step 5: 提交**

```bash
make check
git add src/langharness_core/contracts.py tests/test_contracts.py
git commit -m "核心契约 pin 到 Protocol 类规格并补齐 AgentLoopProvider"
```

---

## Task 9: 核心插件声明迁移（`@Provides`）

**Files:**
- Modify: 18 个核心插件模块（见下表）

- [ ] **Step 1: 逐个替换装饰器与 import**

对下表每个文件：把 `@Provides(SPEC_X)` 改为 `@Provides(<Protocol>)`，并把该文件里对 `SPEC_X` 的 import 换成对应 Protocol 的 import（若常量在同一文件还有别的用途则同时保留）。

| 文件 | 替换 |
| --- | --- |
| `src/langharness_core/plugins/llm/llm.py` | `SPEC_LLM` → `LLMProvider` |
| `src/langharness_core/plugins/tools/tools.py` | `SPEC_TOOL` → `ToolProvider` |
| `src/langharness_core/plugins/tools/workspace.py` | `SPEC_TOOL` → `ToolProvider` |
| `src/langharness_core/plugins/middleware/template_middleware.py` | `SPEC_MIDDLEWARE` → `MiddlewareProvider` |
| `src/langharness_core/plugins/system_prompt/template_system_prompt.py` | `SPEC_SYSTEM_PROMPT` → `SystemPromptProvider` |
| `src/langharness_core/plugins/response_format/template_response_format.py` | `SPEC_RESPONSE_FORMAT` → `ResponseFormatProvider` |
| `src/langharness_core/plugins/state_schema/template_state_schema.py` | `SPEC_STATE_SCHEMA` → `StateSchemaProvider` |
| `src/langharness_core/plugins/context_schema/template_context_schema.py` | `SPEC_CONTEXT_SCHEMA` → `ContextSchemaProvider` |
| `src/langharness_core/plugins/checkpointer/template_checkpointer.py` | `SPEC_CHECKPOINTER` → `CheckpointerProvider` |
| `src/langharness_core/plugins/checkpointer/sqlite.py` | `SPEC_CHECKPOINTER` → `CheckpointerProvider` |
| `src/langharness_core/plugins/store/template_store.py` | `SPEC_STORE` → `StoreProvider` |
| `src/langharness_core/plugins/interrupt_before/template_interrupt_before.py` | `SPEC_INTERRUPT_BEFORE` → `InterruptBeforeProvider` |
| `src/langharness_core/plugins/interrupt_after/template_interrupt_after.py` | `SPEC_INTERRUPT_AFTER` → `InterruptAfterProvider` |
| `src/langharness_core/plugins/debug/template_debug.py` | `SPEC_DEBUG` → `DebugProvider` |
| `src/langharness_core/plugins/name/template_name.py` | `SPEC_NAME` → `NameProvider` |
| `src/langharness_core/plugins/cache/template_cache.py` | `SPEC_CACHE` → `CacheProvider` |
| `src/langharness_core/plugins/transformers/template_transformers.py` | `SPEC_TRANSFORMERS` → `TransformersProvider` |
| `src/langharness_core/plugins/loop/agent_loop.py` | `SPEC_AGENT_LOOP` → `AgentLoopProvider`（`@Requires*` 的迁移在 Task 10 一起做，本步只改 `@Provides`） |

示例（`template_debug.py`）：

```python
from langharness_core.contracts import DebugProvider

@ComponentFactory("debug-plugin-factory")
@Provides(DebugProvider)
class TemplateDebugPlugin:
    ...
```

- [ ] **Step 2: 确认未破坏导入与静态检查**

Run: `.venv/bin/python -m ruff check . && .venv/bin/python -m mypy`
Expected: PASS（ruff 的 F401 会指出残留的未用 SPEC_* import）

- [ ] **Step 3: 跑现有测试**

Run: `.venv/bin/python -m pytest tests/test_e2e.py tests/test_plugins.py -q`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
make check
git add src/langharness_core
git commit -m "核心插件声明迁移到 Protocol 类规格"
```

---

## Task 10: agent loop 绑定守卫

**Files:**
- Modify: `src/langharness_core/plugins/loop/agent_loop.py`
- Modify: `tests/test_e2e.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_e2e.py`（复用该文件的 `descriptors(tmp_path)` 与真实框架装配；注意在文件顶部 import 段补 `from typing import Any` 和 `from langharness_core.contracts import ToolProvider`）：

```python
def test_raw_registered_bad_provider_is_quarantined(tmp_path: Path) -> None:
    registry = descriptors(tmp_path)
    manager = PluginManager(registry)
    manager.start()
    try:
        for item in registry.list():
            manager.install_plugin(item)
        loop = manager.get_service(SPEC_AGENT_LOOP)
        assert loop.describe()["tools"] == ["add"]

        class RawBadToolProvider:
            """多了一个必填参数，签名不满足 ToolProvider。"""

            def get_tools(self, root: str) -> list[Any]:
                return []

            def get_plugin_info(self) -> dict[str, str]:
                return {"name": "raw-bad"}

        manager._context.register_service(ToolProvider, RawBadToolProvider(), {})

        # 坏服务仍在注册表里，但已被隔离出 agent loop 的聚合
        assert manager.get_service("agent.plugin.tools") is not None
        assert loop.describe()["tools"] == ["add"]
        assert len(loop._guards["_tool_providers"].rejected()) == 1
    finally:
        manager.stop()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_e2e.py::test_raw_registered_bad_provider_is_quarantined -q`
Expected: FAIL — `AttributeError: 'PluginAgentLoop' object has no attribute '_guards'`

- [ ] **Step 3: 写实现**

`src/langharness_core/plugins/loop/agent_loop.py`：

import 段把 15 个 `SPEC_*` 常量替换为对应 Protocol（`SPEC_AGENT_LOOP` → `AgentLoopProvider`），并加入：

```python
from langharness_plugin.validation import ContractGuard
```

`__init__` 末尾（在 `self._graph` 之前）加入：

```python
        self._guards: dict[str, ContractGuard] = {
            "_llm_provider": ContractGuard(self, "_llm_provider", LLMProvider),
            "_tool_providers": ContractGuard(
                self, "_tool_providers", ToolProvider
            ),
            "_middleware_providers": ContractGuard(
                self, "_middleware_providers", MiddlewareProvider
            ),
            "_system_prompt_providers": ContractGuard(
                self, "_system_prompt_providers", SystemPromptProvider
            ),
            "_response_format_provider": ContractGuard(
                self, "_response_format_provider", ResponseFormatProvider
            ),
            "_state_schema_provider": ContractGuard(
                self, "_state_schema_provider", StateSchemaProvider
            ),
            "_context_schema_provider": ContractGuard(
                self, "_context_schema_provider", ContextSchemaProvider
            ),
            "_checkpointer_provider": ContractGuard(
                self, "_checkpointer_provider", CheckpointerProvider
            ),
            "_store_provider": ContractGuard(self, "_store_provider", StoreProvider),
            "_interrupt_before_providers": ContractGuard(
                self, "_interrupt_before_providers", InterruptBeforeProvider
            ),
            "_interrupt_after_providers": ContractGuard(
                self, "_interrupt_after_providers", InterruptAfterProvider
            ),
            "_debug_provider": ContractGuard(self, "_debug_provider", DebugProvider),
            "_name_provider": ContractGuard(self, "_name_provider", NameProvider),
            "_cache_provider": ContractGuard(self, "_cache_provider", CacheProvider),
            "_transformers_providers": ContractGuard(
                self, "_transformers_providers", TransformersProvider
            ),
        }
```

每个 BindField 回调在函数体首行插入（示例，`_on_tool_bind`）：

```python
    @BindField("_tool_providers", if_valid=True)
    def _on_tool_bind(self, field: str, service: Any, reference: Any) -> None:
        if not self._guards[field].admit(service):
            return
        self._rebuild()
```

每个 UnbindField 回调在函数体首行插入（示例，`_on_tool_unbind`）：

```python
    @UnbindField("_tool_providers", if_valid=True)
    def _on_tool_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].release(service)
        self._rebuild()
```

其余 14 对回调逐一同上处理（回调名 → 字段）：

| 回调 | 字段 |
| --- | --- |
| `_on_middleware_bind` / `_on_middleware_unbind` | `_middleware_providers` |
| `_on_system_prompt_bind` / `_on_system_prompt_unbind` | `_system_prompt_providers` |
| `_on_response_format_bind` / `_on_response_format_unbind` | `_response_format_provider` |
| `_on_state_schema_bind` / `_on_state_schema_unbind` | `_state_schema_provider` |
| `_on_context_schema_bind` / `_on_context_schema_unbind` | `_context_schema_provider` |
| `_on_checkpointer_bind` / `_on_checkpointer_unbind` | `_checkpointer_provider` |
| `_on_store_bind` / `_on_store_unbind` | `_store_provider` |
| `_on_interrupt_before_bind` / `_on_interrupt_before_unbind` | `_interrupt_before_providers` |
| `_on_interrupt_after_bind` / `_on_interrupt_after_unbind` | `_interrupt_after_providers` |
| `_on_debug_bind` / `_on_debug_unbind` | `_debug_provider` |
| `_on_name_bind` / `_on_name_unbind` | `_name_provider` |
| `_on_cache_bind` / `_on_cache_unbind` | `_cache_provider` |
| `_on_transformers_bind` / `_on_transformers_unbind` | `_transformers_providers` |

`_llm_provider`（`@RequiresBest`，必选）目前在 `agent_loop.py` 里没有 BindField 回调——本 Task 为它补一对，保证坏 LLM 被隔离后 `_rebuild` 看到 None：

```python
    @BindField("_llm_provider", if_valid=True)
    def _on_llm_bind(self, field: str, service: Any, reference: Any) -> None:
        if not self._guards[field].admit(service):
            self._graph = None
            return
        self._rebuild()

    @UnbindField("_llm_provider", if_valid=True)
    def _on_llm_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].release(service)
        self._graph = None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_e2e.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
make check
git add src/langharness_core/plugins/loop/agent_loop.py tests/test_e2e.py
git commit -m "agent loop 绑定期守卫：违规 provider 隔离出聚合且不参与建图"
```

---

## Task 11: API/CLI/Config/Logging/框架层契约 pin 与声明迁移

**Files:**
- Modify: `src/langharness_api/contracts.py`、`src/langharness_cli/contracts.py`、`src/langharness_config/contracts.py`、`src/langharness_logging/contracts.py`、`src/langharness_plugin/contracts.py`
- Modify: 对应插件的 `@Provides`/`@Requires*` 声明

- [ ] **Step 1: pin 各模块协议**

`langharness_api/contracts.py`：给 `RouteProvider`/`AuthProvider`/`RateLimitProvider`/`DBProvider` 加 `@service_contract(SPEC_ROUTE/SPEC_AUTH/SPEC_RATE_LIMIT/SPEC_DB)`；新增并 pin：

```python
@service_contract(SPEC_API_SERVER)
@runtime_checkable
class APIServerProvider(Protocol):
    """Contract implemented by every ``api.server`` service."""

    def build_app(self) -> FastAPI: ...
```

（import 增加 `from fastapi import FastAPI` 与 `from langharness_plugin.validation import service_contract`。）

`langharness_cli/contracts.py`：pin `CLICommandProvider`（`SPEC_CLI_COMMAND`）、`InteractiveRenderer`（`SPEC_CLI_RENDERER`）；`InteractiveCommandContext` 不是服务契约，不 pin。

`langharness_config/contracts.py`：pin `ConfigProvider`（`SPEC_CONFIG_PROVIDER`）、`Configs`（`SPEC_CONFIGS`）。

`langharness_logging/contracts.py`：pin `LogProvider`（`SPEC_LOG`）。

`langharness_plugin/contracts.py`：pin `PluginRegistrar`（`SPEC_PLUGIN_REGISTRAR`）。

- [ ] **Step 2: 迁移声明**

| 文件 | 替换 |
| --- | --- |
| `src/langharness_api/plugins/auth/auth.py` | `@Provides(SPEC_AUTH)` → `@Provides(AuthProvider)` |
| `src/langharness_api/plugins/rate_limit/rate_limit.py` | `SPEC_RATE_LIMIT` → `RateLimitProvider` |
| `src/langharness_api/plugins/db/db.py` | `SPEC_DB` → `DBProvider` |
| `src/langharness_api/plugins/routes/echo.py` / `health.py` / `stream.py` | `@Provides(SPEC_ROUTE)` → `@Provides(RouteProvider)` |
| `src/langharness_api/plugins/server/app.py` | `@Provides(SPEC_API_SERVER)` → `APIServerProvider`；`@Requires` 的 `SPEC_ROUTE`/`SPEC_AUTH`/`SPEC_RATE_LIMIT`/`SPEC_DB`/`SPEC_CONFIGS`/`SPEC_LOG` → `RouteProvider`/`AuthProvider`/`RateLimitProvider`/`DBProvider`/`Configs`/`LogProvider` |
| `src/langharness_api/plugins/routes/stream.py` | `@RequiresBest("_agent_loop", SPEC_AGENT_LOOP, ...)` → `AgentLoopProvider`；`@RequiresBest("_plugin_registrar", SPEC_PLUGIN_REGISTRAR, ...)` → `PluginRegistrar` |
| `src/langharness_config/plugins/configs.py` | `@Provides(SPEC_CONFIGS)` → `Configs`；`@Requires("_providers", SPEC_CONFIG_PROVIDER, ...)` → `ConfigProvider` |
| `src/langharness_config/plugins/toml.py` | `@Provides(SPEC_CONFIG_PROVIDER)` → `ConfigProvider` |
| `src/langharness_logging/plugins/log.py` | `@Provides(SPEC_LOG)` → `LogProvider` |
| `src/langharness_cli/plugins/commands/shell.py`、`model.py`、`health.py` | `@Provides(SPEC_CLI_COMMAND)` → `CLICommandProvider` |
| `src/langharness_cli/plugins/rich_renderer.py` | `@Provides(SPEC_CLI_RENDERER)` → `InteractiveRenderer` |

`PluginManager.start` 的注册改用类规格：

```python
        self._registration = self._context.register_service(
            PluginRegistrar, self, {}
        )
```

- [ ] **Step 3: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_e2e.py tests/test_api_plugins.py tests/test_cli_e2e.py tests/test_logging_plugin.py -q`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
make check
git add src/langharness_api src/langharness_cli src/langharness_config src/langharness_logging src/langharness_plugin
git commit -m "API/CLI/Config/Logging 契约 pin 并迁移服务声明到类规格"
```

---

## Task 12: API 侧守卫与 `/stream` 的 400 归因

**Files:**
- Modify: `src/langharness_api/plugins/server/app.py`、`src/langharness_api/plugins/routes/stream.py`、`src/langharness_config/plugins/configs.py`
- Modify: `tests/test_contract_enforcement.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_contract_enforcement.py`：

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from langharness_api.plugins.server.app import APIServerService
from langharness_api.plugins.routes.stream import StreamRoutePlugin
from langharness_plugin.validation import ContractViolationError, Violation


class _BadRoute:
    def get_router(self, prefix: str):  # 多一个必填参数，不满足 RouteProvider
        return None

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": "bad-route"}


def test_api_server_quarantines_bad_route_provider() -> None:
    component = APIServerService()
    bad = _BadRoute()
    component._route_providers.append(bad)

    assert component._guards["_route_providers"].admit(bad) is False
    assert component._route_providers == []
    assert len(component._guards["_route_providers"].rejected()) == 1


def test_stream_route_reports_contract_violation_as_400() -> None:
    plugin = StreamRoutePlugin()
    plugin._agent_loop = object()

    class _BadRegistrar:
        def ensure_plugin(self, descriptor: PluginDescriptor) -> None:
            raise ContractViolationError(
                plugin=descriptor.name,
                specification=descriptor.specification,
                protocol="LLMProvider",
                violations=(
                    Violation(
                        "agent.plugin.llm",
                        "LLMProvider",
                        "get_model",
                        "MISSING_METHOD",
                        "LLMPlugin.get_model is not implemented",
                    ),
                ),
            )

    plugin._plugin_registrar = _BadRegistrar()
    app = FastAPI()
    app.include_router(plugin.get_router())

    response = TestClient(app).post(
        "/stream",
        json={
            "input": "hi",
            "model": "m",
            "api_key": "k",
            "base_url": "http://localhost",
            "session_id": "s",
        },
    )

    assert response.status_code == 400
    assert "MISSING_METHOD" in response.json()["detail"]
```

（`tests/test_contract_enforcement.py` 顶部已有 `PluginDescriptor` 的 import，`TestClient` 由 FastAPI 提供；`_agent_loop` 只需非 None，路由在 400 分支不会用到它。）

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_contract_enforcement.py -q`
Expected: FAIL — 守卫尚未接线

- [ ] **Step 3: 写实现**

`src/langharness_api/plugins/server/app.py`：

```python
from langharness_plugin.validation import ContractGuard
```

`__init__` 末尾：

```python
        self._guards: dict[str, ContractGuard] = {
            "_route_providers": ContractGuard(self, "_route_providers", RouteProvider),
            "_auth_provider": ContractGuard(self, "_auth_provider", AuthProvider),
            "_rate_limit_provider": ContractGuard(
                self, "_rate_limit_provider", RateLimitProvider
            ),
            "_db_provider": ContractGuard(self, "_db_provider", DBProvider),
            "_configs": ContractGuard(self, "_configs", Configs),
            "_log_provider": ContractGuard(self, "_log_provider", LogProvider),
        }
```

6 对 bind/unbind 回调按 agent loop 同样模式各插一行（bind 首行 `if not self._guards[field].admit(service): return`，unbind 首行 `self._guards[field].release(service)`）。

`src/langharness_config/plugins/configs.py`：`__init__` 加 `self._guard = ContractGuard(self, "_providers", ConfigProvider)`，并在其 `@Requires("_providers", ...)` 上加一对 BindField/UnbindField 回调（当前没有）：

```python
    @BindField("_providers", if_valid=True)
    def _on_provider_bind(self, field: str, service: Any, reference: Any) -> None:
        if not self._guard.admit(service):
            return

    @UnbindField("_providers", if_valid=True)
    def _on_provider_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._guard.release(service)
```

`src/langharness_api/plugins/routes/stream.py`：加两个 guard 与回调插桩（`_agent_loop` → `AgentLoopProvider`、`_plugin_registrar` → `PluginRegistrar`），并在 `ensure_plugin` 外做 400 归因：

```python
from langharness_plugin.validation import ContractGuard, ContractViolationError
...
                try:
                    self._plugin_registrar.ensure_plugin(
                        runtime_llm_descriptor(properties)
                    )
                except ContractViolationError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_contract_enforcement.py tests/test_api_plugins.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
make check
git add src/langharness_api src/langharness_config tests/test_contract_enforcement.py
git commit -m "API 侧服务绑定守卫，/stream 对不合约插件返回 400 归因"
```

---

## Task 13: examples/plugin_demo 最小同步

**Files:**
- Modify: `examples/plugin_demo/contracts.py`、`examples/plugin_demo/plugins/{fake_llm,calculator_tool,logging_middleware}.py`、`examples/plugin_demo/agent_loop.py`

- [ ] **Step 1: contracts.py 改为引用真实核心契约**

```python
"""Demo components consume the real core service contracts."""

from __future__ import annotations

from langharness_core.contracts import (
    SPEC_AGENT_LOOP,
    SPEC_LLM,
    SPEC_MIDDLEWARE,
    SPEC_TOOL,
    AgentLoopProvider,
    LLMProvider,
    MiddlewareProvider,
    ToolProvider,
)

__all__ = [
    "SPEC_AGENT_LOOP",
    "SPEC_LLM",
    "SPEC_MIDDLEWARE",
    "SPEC_TOOL",
    "AgentLoopProvider",
    "LLMProvider",
    "MiddlewareProvider",
    "ToolProvider",
]
```

（`run_demo.py` 继续从 `plugin_demo.contracts` 取字符串常量，无需改动。）

- [ ] **Step 2: 三个 provider 补注解与 `get_protocol`**

`fake_llm.py`：`@Provides(LLMProvider)`；`def get_model(self) -> BaseChatModel:`（`ScriptedToolCallModel` 应已是 `BaseChatModel` 子类，若不是则改用实际基类）；新增

```python
    def get_protocol(self) -> ModelProtocol:
        return "chat"
```

（import `BaseChatModel` 与 `ModelProtocol`。）`calculator_tool.py` / `logging_middleware.py`：`@Provides(ToolProvider/MiddlewareProvider)`，`get_tools(self) -> list[Any]`、`get_middlewares(self) -> list[Any]`、`get_plugin_info(self) -> dict[str, str]`。

- [ ] **Step 3: demo agent loop 用真实协议与守卫**

`agent_loop.py`：`@RequiresBest("_llm_provider", LLMProvider, ...)`、`@Requires("_tool_providers", ToolProvider, ...)`、`@Requires("_middleware_providers", MiddlewareProvider, ...)`；`__init__` 加三个 `ContractGuard`，两对 bind/unbind 回调首行插守卫/释放（`_llm_provider` 无回调则补一对）。`@Provides(SPEC_AGENT_LOOP)` 保持不变。

- [ ] **Step 4: 手动运行验证**

Run: `.venv/bin/python examples/plugin_demo/run_demo.py`
Expected: 输出与原行为一致（安装三个 provider bundle、agent loop 调工具、打印最终回答），无 quarantine ERROR 日志

- [ ] **Step 5: 提交**

```bash
make check
git add examples/plugin_demo
git commit -m "plugin_demo 同步真实契约：provider 补注解，agent loop 加绑定守卫"
```

---

## Task 14: 规则固化与文档

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: AGENTS.md 增加契约规则**

在「Architecture constraints」后追加：

```markdown
### Service contracts

- 每个服务规格都是所属模块 `contracts.py` 里带 `@service_contract(SPEC_X)`
  的 Protocol；`@Provides`/`@Requires`/`@RequiresBest` 一律声明 Protocol 类，
  不写裸 `SPEC_*` 字符串。
- 禁止在 Protocol 类体内写 `__SPECIFICATION__`（会污染 `__protocol_attrs__`
  并让 `isinstance` 失效），pin 由装饰器在类创建后完成。
- 消费方在 BindField 回调里用 `ContractGuard` 守卫注入字段；`PluginManager`
  在安装时硬校验，违规实例被 kill 且不进入绑定集。
- 语义是「调用兼容性」：参数形状必须能被 contract 声明的方式调用，返回注解
  必须声明且允许协变（`dict` 满足 `Mapping`），协议里的 `Any` 处处通配。
```

- [ ] **Step 2: 全量门禁**

Run: `make check`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add AGENTS.md
git commit -m "AGENTS.md 固化服务契约规则"
```

---

## 验收清单

- [ ] `make check` 全绿（ruff、mypy strict、pyright、干净进程导入、pytest ≥95% 覆盖率）。
- [ ] `tests/test_e2e.py` 三协议路径未改行为；`tests/test_contract_enforcement.py` 覆盖安装拒绝、绑定隔离、未 pin 跳过。
- [ ] `git grep -n "get_service_reference(\"agent.plugin.llm\")"` 或等价回归确认字符串规格名仍可解析。
- [ ] `make check` 后手动跑一次 `.venv/bin/python examples/plugin_demo/run_demo.py`。
- [ ] 按 AGENTS.md「Real end-to-end testing」流程跑一轮真实 provider 的 `/stream`，确认无异常（可选，但发布前应做）。
