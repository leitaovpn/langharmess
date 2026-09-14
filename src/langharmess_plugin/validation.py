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
        # 运行时属性可能缺失或不是可调用对象，交由 _method_contract 兜底
        member: Any = getattr(instance, expected.name, None)
        actual = _method_contract(expected.name, member)
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
