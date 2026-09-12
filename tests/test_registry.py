"""Unit tests for plugin descriptors and registry persistence."""
# mypy: ignore-errors
# pyright: reportOptionalMemberAccess=false

from __future__ import annotations

from pathlib import Path

import pytest

from langharmess.registry import PluginDescriptor, PluginRegistry


def make_descriptor(name: str = "llm") -> PluginDescriptor:
    return PluginDescriptor(
        name=name,
        version="1.0.0",
        module=f"langharmess.plugins.{name}",
        factory=f"{name}-factory",
        instance=name,
        specification=f"agent.plugin.{name}",
    )


def test_descriptor_roundtrip() -> None:
    descriptor = PluginDescriptor(
        name="llm",
        version="1.2.3",
        module="langharmess.plugins.llm",
        factory="llm-factory",
        instance="llm",
        specification="agent.plugin.llm",
        ranking=10,
        properties={"model": "fake"},
    )
    assert PluginDescriptor.from_dict(descriptor.to_dict()) == descriptor


def test_registry_add_get_list_and_remove() -> None:
    registry = PluginRegistry()
    registry.add(make_descriptor("llm"))
    registry.add(make_descriptor("tools"))

    assert registry.get("llm").version == "1.0.0"
    assert [item.name for item in registry.list()] == ["llm", "tools"]

    removed = registry.remove("llm")
    assert removed.name == "llm"
    assert registry.get("llm") is None
    assert [item.name for item in registry.list()] == ["tools"]


def test_registry_rejects_duplicate_names() -> None:
    registry = PluginRegistry([make_descriptor("llm")])
    with pytest.raises(ValueError, match="already registered"):
        registry.add(make_descriptor("llm"))


def test_registry_rejects_duplicate_instance_or_factory() -> None:
    registry = PluginRegistry([make_descriptor("llm")])
    duplicate_instance = make_descriptor("other")
    duplicate_instance.instance = "llm"
    with pytest.raises(ValueError, match="instance"):
        registry.add(duplicate_instance)

    duplicate_factory = make_descriptor("other")
    duplicate_factory.factory = "llm-factory"
    with pytest.raises(ValueError, match="factory"):
        registry.add(duplicate_factory)


def test_registry_set_enabled() -> None:
    registry = PluginRegistry([make_descriptor("llm")])
    registry.set_enabled("llm", False)
    assert registry.get("llm").enabled is False


def test_registry_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "plugins.json"
    registry = PluginRegistry([make_descriptor("llm"), make_descriptor("tools")])
    registry.save(path)

    loaded = PluginRegistry.load(path)
    assert [item.name for item in loaded.list()] == ["llm", "tools"]
    assert loaded.get("tools").module == "langharmess.plugins.tools"


def test_registry_load_rejects_unknown_fields() -> None:
    path = Path(__file__).with_name("bad_registry.json")
    path.write_text('{"version":1,"plugins":[{"name":"x"}]}', encoding="utf-8")
    with pytest.raises(ValueError):
        PluginRegistry.load(path)
    path.unlink()


def test_descriptor_from_dict_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="Unknown descriptor fields"):
        PluginDescriptor.from_dict(
            {
                "name": "x",
                "version": "1.0.0",
                "module": "m",
                "factory": "f",
                "instance": "i",
                "specification": "s",
                "surprise": True,
            }
        )


def test_registry_remove_missing_raises_key_error() -> None:
    with pytest.raises(KeyError):
        PluginRegistry().remove("missing")


def test_registry_set_enabled_missing_raises_key_error() -> None:
    with pytest.raises(KeyError):
        PluginRegistry().set_enabled("missing", True)


def test_registry_load_rejects_unsupported_version(tmp_path: Path) -> None:
    path = tmp_path / "plugins.json"
    path.write_text('{"version":2,"plugins":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported"):
        PluginRegistry.load(path)


def test_registry_rejects_invalid_descriptor_values() -> None:
    registry = PluginRegistry()
    with pytest.raises(ValueError, match="text fields"):
        registry.add(make_descriptor(" ").__class__(
            name=" ",
            version="1.0.0",
            module="m",
            factory="f",
            instance="i",
            specification="s",
        ))

    with pytest.raises(ValueError, match="enabled"):
        bad = make_descriptor("bad-enabled")
        bad.enabled = "yes"  # type: ignore[assignment]
        registry.add(bad)

    with pytest.raises(ValueError, match="ranking"):
        bad = make_descriptor("bad-ranking")
        bad.ranking = "high"  # type: ignore[assignment]
        registry.add(bad)
