"""Runtime validation of service objects against their Protocol contracts."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, get_type_hints

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
