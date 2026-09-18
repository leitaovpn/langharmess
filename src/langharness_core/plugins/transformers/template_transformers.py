"""Transformers plugin."""

from __future__ import annotations

from typing import Any

from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharness_core.contracts import TransformersProvider


@ComponentFactory("transformers-plugin-factory")
@Provides(TransformersProvider)
@Property("_plugin_name", "plugin.name", "transformers-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_items", "plugin.transformers", None)
class TemplateTransformersPlugin:
    def __init__(self) -> None:
        self._plugin_name = "transformers-plugin"
        self._plugin_version = "1.0.0"
        self._items: Any = None

    def get_transformers(self) -> list[Any]:
        return list(self._items or [])
