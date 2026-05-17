from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")

from gi.repository import GdkPixbuf, GLib, Gtk

APP_ICON_NAME = "clipboard-manager"
TRAY_ICON_NAME = "clipboard-manager-symbolic"

_PKG_DIR = Path(__file__).resolve().parent
_BUNDLED_ICONS = _PKG_DIR / "data" / "icons"
_REPO_ICONS = _PKG_DIR.parent.parent / "resources" / "icons"


def _icon_search_roots() -> list[Path]:
    roots: list[Path] = []
    if _BUNDLED_ICONS.is_dir():
        roots.append(_BUNDLED_ICONS)
    if _REPO_ICONS.is_dir():
        roots.append(_REPO_ICONS)
    roots.append(Path("/usr/share/icons"))
    return roots


def register_icon_theme_paths() -> None:
    theme = Gtk.IconTheme.get_default()
    if theme is None:
        return
    for root in _icon_search_roots():
        path = str(root)
        paths = theme.get_search_path()
        if path not in paths:
            theme.append_search_path(path)


def resolve_icon_file(name: str) -> Path | None:
    rel = {
        APP_ICON_NAME: Path("hicolor/scalable/apps/clipboard-manager.svg"),
        TRAY_ICON_NAME: Path("hicolor/symbolic/status/clipboard-manager-symbolic.svg"),
    }.get(name)
    if rel is None:
        return None
    for root in _icon_search_roots():
        candidate = root / rel
        if candidate.is_file():
            return candidate
    return None


def load_pixbuf(name: str, size: int) -> GdkPixbuf.Pixbuf | None:
    path = resolve_icon_file(name)
    if path is None:
        return None
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_scale(
            str(path), size, size, True
        )
    except GLib.Error:
        return None


def apply_window_icon(window: Gtk.Window) -> None:
    pb = load_pixbuf(APP_ICON_NAME, 64) or load_pixbuf(TRAY_ICON_NAME, 64)
    if pb is not None:
        window.set_icon(pb)
        return
    theme = Gtk.IconTheme.get_default()
    if theme is not None and theme.has_icon(APP_ICON_NAME):
        window.set_icon_name(APP_ICON_NAME)


def tray_icon_available() -> bool:
    if resolve_icon_file(TRAY_ICON_NAME) is not None:
        return True
    theme = Gtk.IconTheme.get_default()
    return theme is not None and theme.has_icon(TRAY_ICON_NAME)
