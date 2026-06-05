from __future__ import annotations

from pathlib import Path

from platformdirs import PlatformDirs

APP_NAME = "AdvBoxExport"
APP_AUTHOR = "MaldonadoAdv"

_dirs = PlatformDirs(appname=APP_NAME, appauthor=APP_AUTHOR, roaming=True)


def config_dir() -> Path:
    """Diretório de configuração do app (cross-platform).

    Linux:   ~/.config/AdvBoxExport
    macOS:   ~/Library/Application Support/AdvBoxExport
    Windows: %APPDATA%/MaldonadoAdv/AdvBoxExport
    """
    p = Path(_dirs.user_config_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def data_dir() -> Path:
    """Diretório de dados do app (DB, exports, state)."""
    p = Path(_dirs.user_data_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_file() -> Path:
    return config_dir() / "config.json"


def db_file() -> Path:
    return data_dir() / "advbox.db"


def exports_dir() -> Path:
    p = data_dir() / "exports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def state_dir() -> Path:
    p = data_dir() / "state"
    p.mkdir(parents=True, exist_ok=True)
    return p
