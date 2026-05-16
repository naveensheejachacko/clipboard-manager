from __future__ import annotations

import logging
import gi

from winclip.branding import APP_COMMAND

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, Gtk

LOG = logging.getLogger(__name__)

# Presets shown in Settings (pynput GlobalHotKeys format).
HOTKEY_PRESETS: list[tuple[str, str]] = [
    ("Ctrl + Alt + V", "<ctrl>+<alt>+v"),
    ("Ctrl + Shift + V", "<ctrl>+<shift>+v"),
    ("Super + V", "<super>+v"),
]


def theme_icon_name(candidates: list[str], fallback: str = "preferences-system-symbolic") -> str:
    theme = Gtk.IconTheme.get_default()
    for name in candidates:
        if theme.has_icon(name):
            return name
    return fallback


def pin_icon_names(pinned: bool) -> str:
    if pinned:
        return theme_icon_name(
            ["pinned-symbolic", "pin-symbolic", "object-select-symbolic"],
            "emblem-ok-symbolic",
        )
    return theme_icon_name(
        ["pin-symbolic", "window-pin-symbolic", "non-starred-symbolic"],
        "bookmark-new-symbolic",
    )


def gdk_event_to_pynput_combo(event: Gdk.EventKey) -> str | None:
    """Convert a key-press event to a pynput GlobalHotKeys combo string."""
    if event.keyval in (
        Gdk.KEY_Control_L,
        Gdk.KEY_Control_R,
        Gdk.KEY_Alt_L,
        Gdk.KEY_Alt_R,
        Gdk.KEY_Shift_L,
        Gdk.KEY_Shift_R,
        Gdk.KEY_Super_L,
        Gdk.KEY_Super_R,
        Gdk.KEY_Meta_L,
        Gdk.KEY_Meta_R,
        Gdk.KEY_Caps_Lock,
    ):
        return None

    parts: list[str] = []
    state = event.state
    if state & Gdk.ModifierType.CONTROL_MASK:
        parts.append("<ctrl>")
    if state & Gdk.ModifierType.MOD1_MASK:
        parts.append("<alt>")
    if state & Gdk.ModifierType.SHIFT_MASK:
        parts.append("<shift>")
    if state & Gdk.ModifierType.SUPER_MASK or state & Gdk.ModifierType.MOD4_MASK:
        parts.append("<super>")

    name = Gdk.keyval_name(event.keyval)
    if not name:
        return None
    key = name.removeprefix("KP_").lower()
    if key.startswith("unicode"):
        return None
    if len(key) == 1:
        parts.append(key)
    else:
        parts.append(f"<{key}>")
    if not parts:
        return None
    return "+".join(parts)


def validate_pynput_combo(combo: str) -> bool:
    combo = combo.strip()
    if not combo or "+" not in combo:
        return False
    try:
        from pynput import keyboard  # type: ignore[import-untyped]

        parse = getattr(keyboard.HotKey, "parse", None)
        if callable(parse):
            parse(combo)
            return True
        keyboard.GlobalHotKeys({combo: lambda: None})
        return True
    except ImportError:
        # pynput not installed; accept well-formed combos for later use / desktop binding
        return combo.startswith("<") and "+" in combo
    except Exception:  # noqa: BLE001
        return False


class HotkeyCaptureDialog(Gtk.Dialog):
    """Modal dialog: user presses a key combination, then we return the pynput combo."""

    def __init__(self, parent: Gtk.Window, current: str) -> None:
        super().__init__(
            title="Record keyboard shortcut",
            transient_for=parent,
            modal=True,
            destroy_with_parent=True,
        )
        self.add_buttons("_Cancel", Gtk.ResponseType.CANCEL, "_Use", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self._captured: str | None = None

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=14)
        self._status = Gtk.Label(
            label="Press the key combination you want (e.g. Ctrl+Alt+V).",
            xalign=0,
            wrap=True,
        )
        box.pack_start(self._status, False, False, 0)
        self._preview = Gtk.Label(label=f"Current: {current}", xalign=0)
        self._preview.get_style_context().add_class("dim-label")
        box.pack_start(self._preview, False, False, 0)
        self.get_content_area().add(box)

        self.connect("key-press-event", self._on_key_press)
        self.set_can_focus(True)

    def _on_key_press(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        combo = gdk_event_to_pynput_combo(event)
        if combo is None:
            return True
        self._captured = combo
        self._preview.set_text(f"Captured: {combo}")
        self._status.set_text("Press Save, or press another combination to replace it.")
        return True

    def get_captured_combo(self) -> str | None:
        return self._captured


def open_shortcut_setup_help(parent: Gtk.Window) -> None:
    """Show how to bind winclip --toggle in the desktop environment."""
    dlg = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        destroy_with_parent=True,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text="Desktop keyboard shortcut",
    )
    dlg.format_secondary_text(
        "Built-in hotkey (above) uses python3-pynput and works in most sessions.\n\n"
        "Alternatively, add a custom shortcut in your desktop settings:\n"
        "  • Linux Mint / Cinnamon: Settings → Keyboard → Shortcuts → Custom\n"
        "  • Ubuntu GNOME: Settings → Keyboard → Custom Shortcuts\n"
        f"  • Command: {APP_COMMAND} --toggle\n"
        "  • Suggested binding: Ctrl+Alt+V (or Super+V)\n\n"
        "This works even when the built-in hotkey is disabled."
    )
    dlg.run()
    dlg.destroy()


def try_open_system_keyboard_settings() -> bool:
    import shutil
    import subprocess

    candidates = [
        ["cinnamon-settings", "keyboard"],
        ["gnome-control-center", "keyboard"],
        ["xfce4-keyboard-settings"],
        ["mate-keyboard-properties"],
    ]
    for cmd in candidates:
        if shutil.which(cmd[0]):
            try:
                subprocess.Popen(cmd)  # noqa: S603
                return True
            except OSError as exc:
                LOG.debug("Could not run %s: %s", cmd, exc)
    return False
