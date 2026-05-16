from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from winclip.paths import app_config_dir


@dataclass
class AppSettings:
    """User preferences (JSON on disk)."""

    max_entries: int = 120
    max_files_per_clip: int = 100
    store_images: bool = False
    debounce_ms: int = 120
    hotkey_enabled: bool = False
    # pynput key combo, e.g. "<ctrl>+<alt>+v"
    hotkey_combo: str = "<ctrl>+<alt>+v"

    @classmethod
    def default(cls) -> AppSettings:
        return cls()

    @classmethod
    def load(cls, path: Path | None = None) -> AppSettings:
        p = path or (app_config_dir() / "settings.json")
        if not p.is_file():
            return cls.default()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls.default()
        base = cls.default()
        for k, v in raw.items():
            if hasattr(base, k):
                try:
                    setattr(base, k, type(getattr(base, k))(v))
                except (TypeError, ValueError):
                    continue
        return base

    def save(self, path: Path | None = None) -> None:
        p = path or (app_config_dir() / "settings.json")
        p.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
