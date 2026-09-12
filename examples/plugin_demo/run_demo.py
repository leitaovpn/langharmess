"""Run the iPOPO/Pelix/LangChain plugin-driven agent prototype.

Run from the repository root:

    .venv/bin/python examples/plugin_demo/run_demo.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from pelix.framework import create_framework
from pelix.ipopo.constants import SERVICE_IPOPO

EXAMPLES_DIR = Path(__file__).resolve().parent.parent
if str(EXAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLES_DIR))

from plugin_demo.contracts import (  # noqa: E402
    SPEC_AGENT_LOOP,
    SPEC_LLM,
    SPEC_MIDDLEWARE,
    SPEC_TOOL,
)

PROVIDER_BUNDLES = [
    "plugin_demo.plugins.fake_llm",
    "plugin_demo.plugins.calculator_tool",
    "plugin_demo.plugins.logging_middleware",
]
AGENT_LOOP_BUNDLE = "plugin_demo.agent_loop"
REGISTRY_PATH = Path(__file__).with_name("plugin_registry.json")


def wait_for_service(context, specification, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        reference = context.get_service_reference(specification)
        if reference is not None:
            return reference
        time.sleep(0.05)
    raise TimeoutError(f"Service {specification!r} did not appear in {timeout}s")


def service_properties(context, specification):
    refs = context.get_all_service_references(specification) or []
    return [
        {
            "name": ref.get_property("plugin.name"),
            "version": ref.get_property("plugin.version"),
            "ranking": ref.get_property("service.ranking"),
        }
        for ref in refs
    ]


def main():
    framework = create_framework(["pelix.ipopo.core"])
    framework.start()
    context = framework.get_bundle_context()
    ipopo = context.get_service(context.get_service_reference(SERVICE_IPOPO))

    print("== installing provider bundles ==")
    provider_bundles = []
    for module_name in PROVIDER_BUNDLES:
        bundle = context.install_bundle(module_name)
        bundle.start()
        provider_bundles.append(bundle)
        print(f"  installed {module_name} -> bundle {bundle.get_bundle_id()}")

    print("\n== installing agent loop bundle ==")
    loop_bundle = context.install_bundle(AGENT_LOOP_BUNDLE)
    loop_bundle.start()

    loop_ref = wait_for_service(context, SPEC_AGENT_LOOP)
    loop = context.get_service(loop_ref)
    print("\n== resolved plugin services ==")
    print("  llm:", service_properties(context, SPEC_LLM))
    print("  tools:", service_properties(context, SPEC_TOOL))
    print("  middleware:", service_properties(context, SPEC_MIDDLEWARE))
    print("  agent.describe():", loop.describe())

    print("\n== invoking agent (tool should be executed by ToolNode) ==")
    result = loop.invoke("What is 2 + 3?")
    for message in result["messages"]:
        print(f"  {type(message).__name__}: {message.content!r}")

    print("\n== unbinding the calculator tool plugin ==")
    ipopo.kill("calculator-tool")
    print("  agent.describe():", loop.describe())

    print("\n== rebinding the calculator tool plugin ==")
    ipopo.instantiate("calculator-tool-factory", "calculator-tool")
    print("  agent.describe():", loop.describe())

    registry = {
        "version": 1,
        "provider_bundles": PROVIDER_BUNDLES,
        "agent_loop_bundle": AGENT_LOOP_BUNDLE,
        "snapshot": {
            "llm": service_properties(context, SPEC_LLM),
            "tools": service_properties(context, SPEC_TOOL),
            "middleware": service_properties(context, SPEC_MIDDLEWARE),
        },
    }
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    print(f"\n== persisted registry -> {REGISTRY_PATH} ==")

    framework.stop()
    print("done")


if __name__ == "__main__":
    main()
