"""Load ~/.config/nomouse/config.toml with sane defaults."""

import logging
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class Config:
    background_rgba: str = "rgba(0, 0, 0, 0.35)"
    show_hint: bool = True


def _config_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config_home) / "nomouse" / "config.toml"


def load_config() -> Config:
    config = Config()
    path = _config_path()
    if not path.exists():
        return config

    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        log.warning("failed to read config %s: %s, using defaults", path, exc)
        return config

    background_rgba = data.get("background_rgba")
    if isinstance(background_rgba, str):
        config.background_rgba = background_rgba

    show_hint = data.get("show_hint")
    if isinstance(show_hint, bool):
        config.show_hint = show_hint

    return config
