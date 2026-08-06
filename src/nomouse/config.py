"""Load ~/.config/nomouse/config.toml with sane defaults."""

import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class StageGrid:
    cols: int
    rows: int


@dataclass
class Config:
    stage1: StageGrid = field(default_factory=lambda: StageGrid(cols=8, rows=6))
    stage2: StageGrid = field(default_factory=lambda: StageGrid(cols=4, rows=3))
    stage3: StageGrid = field(default_factory=lambda: StageGrid(cols=3, rows=3))
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

    for stage_name in ("stage1", "stage2", "stage3"):
        stage_data = data.get(stage_name)
        if not isinstance(stage_data, dict):
            continue
        default_grid = getattr(config, stage_name)
        cols = stage_data.get("cols", default_grid.cols)
        rows = stage_data.get("rows", default_grid.rows)
        setattr(config, stage_name, StageGrid(cols=cols, rows=rows))

    background_rgba = data.get("background_rgba")
    if isinstance(background_rgba, str):
        config.background_rgba = background_rgba

    show_hint = data.get("show_hint")
    if isinstance(show_hint, bool):
        config.show_hint = show_hint

    return config
