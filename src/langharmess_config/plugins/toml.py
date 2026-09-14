"""TOML-backed configuration provider."""

from __future__ import annotations

import tomllib
from importlib.resources import files
from pathlib import Path
from typing import Any

from pelix.ipopo.decorators import ComponentFactory, Property, Provides, Validate

from langharmess_config.contracts import ConfigProvider


@ComponentFactory("toml-config-plugin-factory")
@Provides(ConfigProvider)
@Property(
    "_config_path",
    "plugin.config.path",
    "~/.langharmess/langharmess.toml",
)
class TOMLConfigPlugin:
    """Creates the user config from the packaged template and reads it."""

    def __init__(self) -> None:
        self._config_path = "~/.langharmess/langharmess.toml"

    @Validate
    def _validate(self, bundle_context: Any) -> None:
        self._ensure_config()

    def get_config(self) -> dict[str, Any]:
        with self._ensure_config().open("rb") as stream:
            return tomllib.load(stream)

    def _ensure_config(self) -> Path:
        path = Path(self._config_path).expanduser()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            template = files("langharmess_config").joinpath(
                "config/langharmess.toml"
            )
            path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        return path
