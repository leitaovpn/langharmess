"""Runtime validation of service objects against their Protocol contracts."""

from __future__ import annotations

import inspect
import logging
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, get_args, get_origin, get_type_hints

LOGGER = logging.getLogger("langharmess.contract")

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


def _origin(annotation: Any) -> Any:
    origin = get_origin(annotation)
    return typing.Union if origin is types.UnionType else origin


def _annotations_match(expected: Any, actual: Any, *, covariance: bool = False) -> bool:
    """Check an actual annotation against the expected one.

    匹配规则按顺序执行：
    1. ``Any``/``None``（注解缺失）在任意深度都是通配：出现在任一侧即视为匹配；
    2. 注解相等（``X | None`` 与 ``Optional[X]`` 视为相等）直接通过；
    3. ``Callable[[...], R]`` 的参数列表按元素逐项比对；
    4. union 方向：参数位置要求 expected 的每个分支都被 actual 的某个分支覆盖
       （实现可以加宽入参）；返回位置（``covariance=True``）要求 actual 的每个分支
       都被 expected 的某个分支覆盖（实现可以收窄返回值）；非 union 一侧视作单分支；
    5. origin 不一致只在返回位置经 ``issubclass`` 容忍（``dict`` 满足 ``Mapping``，
       普通类允许返回子类），Protocol 等不可 issubclass 的情形视为不匹配；
    6. origin 一致时递归比对类型参数，任一侧未参数化（如裸 ``typing.List``）视为通过。
    """
    if expected is Any or expected is None:
        return True
    if actual is Any or actual is None:
        return True
    if expected == actual:
        return True
    if isinstance(expected, list) or isinstance(actual, list):
        # Callable 的参数列表是普通 list：逐项比对
        return (
            isinstance(expected, list)
            and isinstance(actual, list)
            and len(expected) == len(actual)
            and all(
                _annotations_match(item, other, covariance=covariance)
                for item, other in zip(expected, actual)
            )
        )
    expected_origin = _origin(expected)
    actual_origin = _origin(actual)
    expected_args = get_args(expected)
    actual_args = get_args(actual)
    expected_is_union = expected_origin is typing.Union
    actual_is_union = actual_origin is typing.Union
    if expected_is_union or actual_is_union:
        # 非 union 一侧视作单分支，覆盖 ``X | None`` 与 ``X`` 这类混合作比较
        expected_arms = expected_args if expected_is_union else (expected,)
        actual_arms = actual_args if actual_is_union else (actual,)
        if covariance:
            # 返回位置允许收窄：actual 的每个分支都要被 expected 覆盖
            return all(
                any(
                    _annotations_match(expected_arm, actual_arm, covariance=True)
                    for expected_arm in expected_arms
                )
                for actual_arm in actual_arms
            )
        return all(
            any(
                _annotations_match(expected_arm, actual_arm, covariance=covariance)
                for actual_arm in actual_arms
            )
            for expected_arm in expected_arms
        )
    if expected_origin is None or actual_origin is None:
        if covariance and isinstance(expected, type) and isinstance(actual, type):
            try:
                return issubclass(actual, expected)
            except TypeError:
                return False
        return False
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


def _parameter_problems(
    expected: MethodContract, actual: MethodContract
) -> list[tuple[ViolationCode, str]]:
    """Check the parameters of one method pair for call compatibility.

    契约参数在实现侧缺失时，只有 ``*args``（位置方向）或 ``**kwargs``（关键字方向）
    能吸收；实现侧多出的必填参数按位置对齐判断：契约的位置参数会落在实现侧同序
    位置，仅名字不同不重复报告，超出契约位置参数个数的才算冲突。
    """
    problems: list[tuple[ViolationCode, str]] = []
    by_name = {parameter.name: parameter for parameter in actual.parameters}
    for parameter in expected.parameters:
        match = by_name.get(parameter.name)
        if match is not None:
            if (parameter.positional and not match.positional) or (
                parameter.keyword and not match.keyword
            ):
                direction = (
                    "positional"
                    if parameter.positional and not match.positional
                    else "keyword"
                )
                problems.append(
                    (
                        "PARAM_KIND_CONFLICT",
                        f"parameter {parameter.name!r} cannot be passed as {direction}",
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
    positional_expected = sum(
        1 for parameter in expected.parameters if parameter.positional
    )
    # 参数表中的位置参数恒为前缀，故 enumerate 序号即位置序号：契约按位置传入的
    # 参数会填满实现侧同序参数，只有超出该范围的多余必填参数才强制调用方额外传参
    for index, parameter in enumerate(actual.parameters):
        if parameter.name in expected_names or parameter.has_default:
            continue
        if parameter.positional and index < positional_expected:
            continue
        problems.append(
            (
                "PARAM_EXTRA_REQUIRED",
                f"parameter {parameter.name!r} has no default and is not part of the contract",
            )
        )
    return problems


def validate(instance: Any, protocol: type[Any]) -> tuple[Violation, ...]:
    """Check an instance against a pinned contract and return all violations."""
    contract = describe(protocol)
    specification = contract.specification or contract.name
    violations: list[Violation] = []
    for expected in contract.methods:
        if expected.error is not None:
            violations.append(
                Violation(
                    specification,
                    contract.name,
                    expected.name,
                    "UNRESOLVED_SIGNATURE",
                    expected.error,
                )
            )
            continue
        member: Any = getattr(instance, expected.name, None)
        if member is None:
            violations.append(
                Violation(
                    specification,
                    contract.name,
                    expected.name,
                    "MISSING_METHOD",
                    f"{contract.name}.{expected.name} is not implemented",
                )
            )
            continue
        if not callable(member):
            violations.append(
                Violation(
                    specification,
                    contract.name,
                    expected.name,
                    "NOT_CALLABLE",
                    f"{contract.name}.{expected.name} is not callable",
                )
            )
            continue
        actual = _method_contract(expected.name, member)
        if actual.error is not None:
            violations.append(
                Violation(
                    specification,
                    contract.name,
                    expected.name,
                    "UNRESOLVED_SIGNATURE",
                    actual.error,
                )
            )
            continue
        for code, detail in _parameter_problems(expected, actual):
            violations.append(
                Violation(specification, contract.name, expected.name, code, detail)
            )
        if (
            expected.return_annotation is not None
            and expected.return_annotation is not Any
        ):
            if actual.return_annotation is None:
                violations.append(
                    Violation(
                        specification,
                        contract.name,
                        expected.name,
                        "RETURN_ANNOTATION_MISSING",
                        f"expected {expected.return_annotation!r}",
                    )
                )
            elif not _annotations_match(
                expected.return_annotation, actual.return_annotation, covariance=True
            ):
                violations.append(
                    Violation(
                        specification,
                        contract.name,
                        expected.name,
                        "RETURN_ANNOTATION_MISMATCH",
                        f"{actual.return_annotation!r} does not satisfy "
                        f"{expected.return_annotation!r}",
                    )
                )
        by_name = {parameter.name: parameter for parameter in actual.parameters}
        for parameter in expected.parameters:
            actual_parameter = by_name.get(parameter.name)
            if actual_parameter is None or parameter.annotation is None:
                continue
            if not _annotations_match(parameter.annotation, actual_parameter.annotation):
                violations.append(
                    Violation(
                        specification,
                        contract.name,
                        expected.name,
                        "PARAM_ANNOTATION_MISMATCH",
                        f"parameter {parameter.name!r} is "
                        f"{actual_parameter.annotation!r}, expected "
                        f"{parameter.annotation!r}",
                    )
                )
    return tuple(violations)
