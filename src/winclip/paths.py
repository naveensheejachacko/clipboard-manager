from __future__ import annotations

import os
from pathlib import Path


def xdg_data_home() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base)
    return Path.home() / ".local" / "share"


def xdg_config_home() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base)
    return Path.home() / ".config"


def xdg_cache_home() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    if base:
        return Path(base)
    return Path.home() / ".cache"


def app_data_dir() -> Path:
    d = xdg_data_home() / "winclip"
    d.mkdir(parents=True, exist_ok=True)
    return d


def app_config_dir() -> Path:
    d = xdg_config_home() / "winclip"
    d.mkdir(parents=True, exist_ok=True)
    return d


def app_images_dir() -> Path:
    d = app_data_dir() / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return app_data_dir() / "history.sqlite3"


def log_path() -> Path:
    return app_data_dir() / "winclip.log"


def ipc_socket_path() -> Path:
    """AF_UNIX path for secondary-instance commands (toggle, prefs)."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / "winclip.sock"
    return Path("/tmp") / f"winclip-{os.getuid()}.sock"
