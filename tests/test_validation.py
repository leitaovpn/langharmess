"""Unit tests for runtime service contract validation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Optional, Protocol, runtime_checkable

import pytest

from langharmess_plugin.validation import (
    CONTRACTS,
    contract_for,
    describe,
    service_contract,
    validate,
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


def test_describe_reports_pinned_specification() -> None:
    assert describe(DemoProvider).specification == "test.contract.demo"


class _NestedAny(Protocol):
    def run(self, value: list[Any]) -> list[Any]: ...


# 注解在 get_type_hints 中按模块全局解析，普通类必须定义在模块层
class _ShapeBase:
    pass


class _ShapeChild(_ShapeBase):
    pass


class _OtherShape:
    pass


def test_any_is_a_wildcard_at_every_depth() -> None:
    class Concrete:
        def run(self, value: list[object]) -> list[str]:
            return []

    assert validate(Concrete(), _NestedAny) == ()


def test_any_wildcards_inside_callable_parameter_lists() -> None:
    class Expected(Protocol):
        # 契约侧有意保留字符串注解写法：get_type_hints 必须能解析
        def run(self) -> "Callable[[Any], str]": ...  # noqa: UP037

    class Concrete:
        def run(self) -> Callable[[int], str]:
            return str

    assert validate(Concrete(), Expected) == ()


def test_optional_matches_union_spelling() -> None:
    # Optional 必须能经模块全局解析：get_type_hints 看不到函数内局部导入
    class Expected(Protocol):
        def run(self) -> int | None: ...

    class Concrete:
        # 本用例就是要验证 Optional[X] 与 X | None 等价，保留旧式拼写
        def run(self) -> Optional[int]:  # noqa: UP045
            return None

    assert validate(Concrete(), Expected) == ()


def test_return_annotation_allows_covariance() -> None:
    class Expected(Protocol):
        def run(self) -> Mapping[str, Any]: ...

    class Concrete:
        def run(self) -> dict[str, Any]:
            return {}

    assert validate(Concrete(), Expected) == ()


def test_mismatched_return_annotation_is_reported() -> None:
    class Expected(Protocol):
        def run(self) -> list[str]: ...

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


def test_any_actual_annotation_is_accepted() -> None:
    class Expected(Protocol):
        def run(self, value: list[int]) -> int: ...

    class Concrete:
        def run(self, value: list[Any]) -> int:
            return 0

    assert validate(Concrete(), Expected) == ()


def test_union_annotations_compare_arm_wise() -> None:
    # 返回位置 union 按协变方向比对：实现侧每个分支被契约覆盖即可，允许收窄。
    # 旧用例断言的 `int | str | None` 对 `int | str` 契约（加宽）通过，方向反了；
    # 新语义下该加宽非法，由 test_return_union_may_not_widen 覆盖。
    class Expected(Protocol):
        def run(self) -> int | str | None: ...

    class Concrete:
        def run(self) -> int | str:
            return 0

    assert validate(Concrete(), Expected) == ()


def test_return_union_may_narrow() -> None:
    class Expected(Protocol):
        def run(self) -> "str | None": ...  # noqa: UP037

    class Concrete:
        def run(self) -> str:
            return ""

    assert validate(Concrete(), Expected) == ()


def test_return_union_may_not_widen() -> None:
    class Expected(Protocol):
        def run(self) -> "int | str": ...  # noqa: UP037

    class Concrete:
        def run(self) -> "int | str | None":  # noqa: UP037
            return None

    codes = [violation.code for violation in validate(Concrete(), Expected)]
    assert codes == ["RETURN_ANNOTATION_MISMATCH"]


def test_union_arm_absent_from_actual_is_reported() -> None:
    class Expected(Protocol):
        def run(self) -> int | str: ...

    class Concrete:
        def run(self) -> int | None:
            return None

    codes = [violation.code for violation in validate(Concrete(), Expected)]
    assert codes == ["RETURN_ANNOTATION_MISMATCH"]


def test_parameter_annotations_are_invariant() -> None:
    class Expected(Protocol):
        def run(self, value: Mapping[str, Any]) -> None: ...

    class Concrete:
        def run(self, value: dict[str, Any]) -> None: ...

    codes = [violation.code for violation in validate(Concrete(), Expected)]
    assert codes == ["PARAM_ANNOTATION_MISMATCH"]


def test_parameter_union_may_widen() -> None:
    class Expected(Protocol):
        def run(self, value: "int | str") -> None: ...  # noqa: UP037

    class Concrete:
        def run(self, value: "int | str | None") -> None: ...  # noqa: UP037

    assert validate(Concrete(), Expected) == ()


def test_return_plain_class_allows_subclass() -> None:
    class Expected(Protocol):
        def run(self) -> _ShapeBase: ...

    class Concrete:
        def run(self) -> _ShapeChild:
            return _ShapeChild()

    assert validate(Concrete(), Expected) == ()


def test_return_plain_class_rejects_unrelated() -> None:
    class Expected(Protocol):
        def run(self) -> _ShapeBase: ...

    class Concrete:
        def run(self) -> _OtherShape:
            return _OtherShape()

    codes = [violation.code for violation in validate(Concrete(), Expected)]
    assert codes == ["RETURN_ANNOTATION_MISMATCH"]


def test_covariance_rejects_unrelated_return_origin() -> None:
    class Expected(Protocol):
        def run(self) -> Mapping[str, Any]: ...

    class Concrete:
        def run(self) -> list[Any]:
            return []

    codes = [violation.code for violation in validate(Concrete(), Expected)]
    assert codes == ["RETURN_ANNOTATION_MISMATCH"]


def test_return_annotation_arity_mismatch_is_reported() -> None:
    class Expected(Protocol):
        def run(self) -> tuple[str, int]: ...

    class Concrete:
        def run(self) -> tuple[str]:
            return ("x",)

    codes = [violation.code for violation in validate(Concrete(), Expected)]
    assert codes == ["RETURN_ANNOTATION_MISMATCH"]


def test_missing_return_annotation_is_reported() -> None:
    class Expected(Protocol):
        def run(self) -> str: ...

    class Concrete:
        def run(self):  # type: ignore[no-untyped-def]
            return "value"

    codes = [violation.code for violation in validate(Concrete(), Expected)]
    assert codes == ["RETURN_ANNOTATION_MISSING"]


def test_unannotated_contract_parameter_is_skipped() -> None:
    class Loose(Protocol):
        def run(self, value) -> int: ...  # type: ignore[no-untyped-def]

    class Concrete:
        def run(self, value: str) -> int:
            return 0

    assert validate(Concrete(), Loose) == ()


def test_unannotated_parameter_is_tolerated() -> None:
    class Expected(Protocol):
        def run(self, value: int) -> None: ...

    class Concrete:
        # 返回侧仍须标注：契约声明 -> None 时缺返回注解会触发 RETURN_ANNOTATION_MISSING，
        # 本用例只验证参数侧未注解被容忍
        def run(self, value) -> None:  # type: ignore[no-untyped-def]
            return None

    assert validate(Concrete(), Expected) == ()


def test_unresolvable_contract_annotation_is_reported() -> None:
    def broken(self, value: MissingName) -> None: ...  # type: ignore[name-defined, no-untyped-def]  # noqa: F821

    protocol_class = type("BrokenProvider", (Protocol,), {"broken": broken})  # type: ignore[arg-type]

    codes = [violation.code for violation in validate(_Implementation(), protocol_class)]
    assert codes == ["UNRESOLVED_SIGNATURE"]


class _Tool(Protocol):
    # 契约侧有意保留字符串注解写法：get_type_hints 必须能解析
    def get_tools(self) -> "list[Any]": ...  # noqa: UP037

    def get_plugin_info(self) -> "dict[str, str]": ...  # noqa: UP037


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


def test_parameter_union_may_widen_from_plain() -> None:
    class Expected(Protocol):
        def run(self, value: int) -> None: ...

    class Concrete:
        def run(self, value: "int | str | None") -> None: ...  # noqa: UP037

    assert _codes(Concrete(), Expected) == []


class _NotRuntimeProtocol(Protocol):
    def run(self) -> None: ...


def test_non_runtime_protocol_return_degrades_to_mismatch() -> None:
    class Expected(Protocol):
        def run(self) -> _NotRuntimeProtocol: ...

    class Concrete:
        def run(self) -> _ShapeChild:
            return _ShapeChild()

    assert _codes(Concrete(), Expected) == ["RETURN_ANNOTATION_MISMATCH"]


def test_unresolvable_implementation_signature_is_reported() -> None:
    class BadSignature:
        __signature__ = "not a signature"

        def __call__(self) -> None: ...

    class Expected(Protocol):
        def run(self) -> None: ...

    class Concrete:
        run = BadSignature()

    assert _codes(Concrete(), Expected) == ["UNRESOLVED_SIGNATURE"]
