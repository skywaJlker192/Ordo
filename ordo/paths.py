from __future__ import annotations

import os
from pathlib import Path


def ordo_home() -> Path:
    """Папка с данными Ordo. Переопределяется переменной ORDO_HOME."""
    env = os.environ.get("ORDO_HOME")
    return Path(env).expanduser() if env else Path.home() / ".ordo"


def config_path() -> Path:
    return ordo_home() / "config.json"


def db_path() -> Path:
    return ordo_home() / "ordo.db"


def trash_dir() -> Path:
    return ordo_home() / "trash"


def expand(value: str) -> Path:
    """~ и переменные окружения (%USERPROFILE%, $HOME) -> Path."""
    return Path(os.path.expandvars(os.path.expanduser(str(value))))
