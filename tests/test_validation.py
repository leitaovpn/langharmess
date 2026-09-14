"""Unit tests for runtime service contract validation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pytest

from langharmess_plugin.validation import (
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
