"""INI-backed configuration provider."""

from __future__ import annotations

import configparser
from importlib.resources import files
from pathlib import Path

from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess_config.contracts import SPEC_CONFIG_PROVIDER


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

    def get_config(self) -> dict[str, dict[str, str]]:
        path = self._ensure_config()
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(path, encoding="utf-8")
        config = {"DEFAULT": dict(parser.defaults())}
        for section in parser.sections():
            config[section] = dict(parser.items(section, raw=True))
        return config

    def _ensure_config(self) -> Path:
        path = Path(self._config_path).expanduser()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            template = files("langharmess_config").joinpath("config/langharmess.ini")
            path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        return path
