"""A real dynamic plugin bundle used by the e2e discovery test."""

from __future__ import annotations

from typing import Any

from pelix.ipopo.decorators import ComponentFactory, Provides

from langharmess_plugin.contracts import ToolExportTarget


@ComponentFactory("dynamic-echo-factory")
@Provides(ToolExportTarget)
class DynamicEcho:
    def invoke_export(self, operation: str, arguments: dict[str, Any]) -> Any:
        return {"operation": operation, "arguments": arguments}
