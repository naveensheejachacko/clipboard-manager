from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk

from winclip.branding import APP_COMMAND, APP_DISPLAY_NAME
from winclip.hotkey_util import theme_icon_name

if TYPE_CHECKING:
    from winclip.app import WinclipApplication

LOG = logging.getLogger(__name__)

_TRAY_ICON = theme_icon_name(
    ["edit-paste-symbolic", "edit-paste", "clipboard-symbolic"],
    "edit-paste",
)


class TrayIcon:
    """System tray icon (AppIndicator on Mint/Ubuntu, else Gtk.StatusIcon)."""

    def __init__(self, app: WinclipApplication) -> None:
        self._app = app
        self._status_icon: Gtk.StatusIcon | None = None
        self._indicator = None
        self._menu = self._build_menu()
        if not self._try_appindicator():
            self._try_status_icon()

    def _build_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        show_item = Gtk.MenuItem(label="Show history")
        show_item.connect("activate", lambda _i: self._app.show_history())
        menu.append(show_item)

        prefs_item = Gtk.MenuItem(label="Settings")
        prefs_item.connect("activate", lambda _i: self._app.open_preferences())
        menu.append(prefs_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label=f"Quit {APP_DISPLAY_NAME}")
        quit_item.connect("activate", lambda _i: self._app.quit_app())
        menu.append(quit_item)

        menu.show_all()
        return menu

    def _try_appindicator(self) -> bool:
        try:
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3 as AppIndicator
        except (ImportError, ValueError):
            try:
                gi.require_version("AppIndicator3", "0.1")
                from gi.repository import AppIndicator3 as AppIndicator
            except (ImportError, ValueError):
                return False

        try:
            ind = AppIndicator.Indicator.new(
                "clipboard-manager",
                _TRAY_ICON,
                AppIndicator.IndicatorCategory.APPLICATION_STATUS,
            )
            ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
            ind.set_title(APP_DISPLAY_NAME)
            ind.set_menu(self._menu)
            self._indicator = ind
            LOG.info("Tray: using AppIndicator")
            return True
        except Exception as exc:  # noqa: BLE001
            LOG.warning("AppIndicator tray failed: %s", exc)
            return False

    def _try_status_icon(self) -> None:
        try:
            icon = Gtk.StatusIcon.new_from_icon_name(_TRAY_ICON, Gtk.IconSize.MENU)
            icon.set_tooltip_text(f"{APP_DISPLAY_NAME} — click to show history")
            icon.connect("activate", self._on_status_activate)
            icon.connect("popup-menu", self._on_status_popup)
            icon.set_visible(True)
            self._status_icon = icon
            LOG.info("Tray: using Gtk.StatusIcon")
        except Exception as exc:  # noqa: BLE001
            LOG.warning("StatusIcon tray failed: %s", exc)

    def _on_status_activate(self, _icon: Gtk.StatusIcon) -> None:
        self._app.toggle_history_window()

    def _on_status_popup(
        self, _icon: Gtk.StatusIcon, button: int, activate_time: int
    ) -> None:
        self._menu.popup(None, None, None, None, button, activate_time)

    def destroy(self) -> None:
        if self._status_icon is not None:
            self._status_icon.set_visible(False)
            self._status_icon = None
        self._indicator = None
