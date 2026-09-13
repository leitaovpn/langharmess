"""INI-backed configuration provider."""

from __future__ import annotations

import configparser
from importlib.resources import files
from pathlib import Path
from typing import Any

from pelix.ipopo.decorators import ComponentFactory, Property, Provides, Validate

from langharmess_config.contracts import SPEC_CONFIG_PROVIDER


def _strip_quotes(value: str) -> str:
    """Remove a matching pair of surrounding quotes from an INI value."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


@ComponentFactory("ini-config-plugin-factory")
@Provides(SPEC_CONFIG_PROVIDER)
@Property(
    "_config_path",
    "plugin.config.path",
    "~/.langharmess/langharmess.ini",
)
class INIConfigPlugin:
    """Creates the user config from the packaged template and reads it."""

    def __init__(self) -> None:
        self._config_path = "~/.langharmess/langharmess.ini"

    @Validate
    def _validate(self, bundle_context: Any) -> None:
        self._ensure_config()

    def get_config(self) -> dict[str, dict[str, str]]:
        path = self._ensure_config()
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(path, encoding="utf-8")
        config = {"DEFAULT": dict(parser.defaults())}
        for section in parser.sections():
            config[section] = {
                key: _strip_quotes(value)
                for key, value in parser.items(section, raw=True)
            }
        return config

    def _ensure_config(self) -> Path:
        path = Path(self._config_path).expanduser()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            template = files("langharmess_config").joinpath("config/langharmess.ini")
            path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        return path
