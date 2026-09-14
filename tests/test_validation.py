"""Unit tests for runtime service contract validation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pytest

from langharmess_plugin.validation import (
    CONTRACTS,
    contract_for,
    describe,
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
    assert DemoProvider.__SPECIFICATION__ == "test.contract.demo"  # type: ignore[attr-defined]
    assert contract_for("test.contract.demo") is DemoProvider
    assert CONTRACTS["test.contract.demo"] is DemoProvider


def test_service_contract_keeps_isinstance_semantics() -> None:
    # 类体内写 __SPECIFICATION__ 会污染 __protocol_attrs__ 并让 isinstance 失效
    assert "__SPECIFICATION__" not in DemoProvider.__protocol_attrs__  # type: ignore[attr-defined]
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
    # 故意的未定义注解：验证 get_type_hints 解析失败被转成 error 而不抛出
    def broken(self, value: MissingName) -> None: ...  # type: ignore[name-defined, no-untyped-def]  # noqa: F821

    namespace = {"broken": broken}
    # Protocol 是 typing 特殊形式而非真实类，动态建类时类型检查器看不懂
    contract_class = type("BrokenProfile", (Protocol,), namespace)  # type: ignore[arg-type]

    method = describe(contract_class).methods[0]
    assert method.error is not None
    assert "MissingName" in method.error


def test_describe_caches_result() -> None:
    assert describe(_Shape) is describe(_Shape)
