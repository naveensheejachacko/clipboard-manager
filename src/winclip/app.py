from __future__ import annotations

import logging
import socket
import threading
import urllib.parse
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

from winclip.branding import APP_COMMAND, APP_DISPLAY_NAME
from winclip.clipboard_io import set_clipboard_image, write_thumbnail
from winclip.db import ClipEntry, Database, stable_hash
from winclip.hotkey_util import (
    HOTKEY_PRESETS,
    HotkeyCaptureDialog,
    open_shortcut_setup_help,
    pin_icon_names,
    theme_icon_name,
    try_open_system_keyboard_settings,
    validate_pynput_combo,
)
from winclip.paths import app_images_dir, db_path, ipc_socket_path
from winclip.settings import AppSettings
from winclip.tray import TrayIcon
from winclip.icons import apply_window_icon, register_icon_theme_paths
from winclip.ui_style import apply_winclip_theme, style_widget

LOG = logging.getLogger(__name__)

_ROW_HEIGHT = 44
_ROW_ICON_SIZE = Gtk.IconSize.BUTTON


def _kind_icon_name(kind: str) -> str:
    if kind == "image":
        return theme_icon_name(
            ["image-x-generic-symbolic", "image-loading-symbolic"],
            "insert-image-symbolic",
        )
    if kind == "uris":
        return theme_icon_name(
            ["folder-symbolic", "inode-directory-symbolic"],
            "folder-symbolic",
        )
    return theme_icon_name(
        ["text-x-generic-symbolic", "text-x-generic"],
        "text-x-generic-symbolic",
    )


def _gtk_clipboard_targets_to_atoms(
    atoms: object | None, n_atoms: object | None
) -> list:
    """Normalize GtkClipboardTargetsReceivedFunc atoms across PyGObject versions."""
    if atoms is None:
        return []
    atom_list: list = []
    try:
        if isinstance(atoms, (str, bytes)):
            return []
        atom_list = list(atoms)
    except TypeError:
        atom_list = [atoms]
    if isinstance(n_atoms, int) and n_atoms > 0:
        atom_list = atom_list[:n_atoms]
    return atom_list


def parse_uri_list(data: str, max_files: int) -> tuple[list[str], bool]:
    paths: list[str] = []
    truncated = False
    for line in data.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("file://"):
            p = urllib.parse.unquote(urllib.parse.urlparse(line).path)
            paths.append(p)
        elif line.startswith("/"):
            paths.append(line)
        if len(paths) >= max_files:
            truncated = True
            break
    return paths, truncated


def parse_gnome_copied_files(data: str, max_files: int) -> tuple[list[str], bool]:
    """Parse x-special/gnome-copied-files (Nemo/Cinnamon file copy)."""
    paths: list[str] = []
    truncated = False
    lines = data.splitlines()
    start = 1 if lines and lines[0].strip().lower() in ("copy", "cut") else 0
    for line in lines[start:]:
        line = line.strip()
        if not line:
            continue
        if line.startswith("file://"):
            p = urllib.parse.unquote(urllib.parse.urlparse(line).path)
            paths.append(p)
        elif line.startswith("/"):
            paths.append(line)
        if len(paths) >= max_files:
            truncated = True
            break
    return paths, truncated


class WinclipApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="io.github.clipboard-manager")
        self._db = Database(db_path())
        self._settings = AppSettings.load()
        self._window: Gtk.ApplicationWindow | None = None
        self._ignore_clipboard_until_ms: int = 0
        self._debounce_id: int = 0
        self._clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self._hotkey_listener: object | None = None
        self._hotkey_thread: threading.Thread | None = None
        self._ipc_sock: socket.socket | None = None
        self._ipc_thread: threading.Thread | None = None
        self._ipc_stop = threading.Event()
        self._open_prefs_on_launch: bool = False
        self._start_hidden: bool = False
        self._tray: TrayIcon | None = None
        self._held: bool = False

        self.connect("activate", self._on_activate)
        self.connect("shutdown", self._on_shutdown)
        self._clipboard.connect("owner-change", self._on_clipboard_owner_change)

    def set_open_prefs_on_launch(self, value: bool) -> None:
        self._open_prefs_on_launch = bool(value)

    def set_start_hidden(self, value: bool) -> None:
        """Start in tray only (no window) — for autostart."""
        self._start_hidden = bool(value)

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        register_icon_theme_paths()
        self._start_ipc_server()
        self._tray = TrayIcon(self)
        self.hold()
        self._held = True

    def show_history(self) -> None:
        self.activate()

    def open_preferences(self) -> None:
        self._open_prefs()

    def toggle_history_window(self) -> None:
        self._toggle_window()

    def quit_app(self) -> None:
        if self._held:
            self.release()
            self._held = False
        self.quit()

    def mark_ignore_clipboard(self, ms: int = 450) -> None:
        now = GLib.get_monotonic_time() // 1000
        self._ignore_clipboard_until_ms = now + ms

    def _on_shutdown(self, _app: Gtk.Application) -> None:
        self._ipc_stop.set()
        if self._ipc_sock is not None:
            try:
                self._ipc_sock.close()
            except OSError:
                pass
            self._ipc_sock = None
        if self._ipc_thread is not None:
            self._ipc_thread.join(timeout=2.0)
            self._ipc_thread = None
        try:
            ipc_socket_path().unlink(missing_ok=True)
        except OSError:
            pass

    def _start_ipc_server(self) -> None:
        path = ipc_socket_path()
        try:
            if path.exists() or path.is_socket():
                path.unlink()
        except OSError:
            pass
        try:
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(str(path))
            srv.listen(8)
        except OSError as exc:
            LOG.warning(
                f"IPC server not started (%s); {APP_COMMAND} --toggle only works while this process runs.",
                exc,
            )
            return
        self._ipc_sock = srv
        self._ipc_stop.clear()
        app = self

        def _ipc_loop() -> None:
            sock = srv
            while not app._ipc_stop.is_set():
                try:
                    sock.settimeout(0.5)
                    conn, _addr = sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                data = b""
                try:
                    conn.settimeout(0.25)
                    data = conn.recv(4096)
                except OSError:
                    data = b""
                finally:
                    try:
                        conn.close()
                    except OSError:
                        pass
                if b"TOGGLE" in data:
                    GLib.idle_add(app._toggle_window)
                elif b"PREFS" in data:
                    GLib.idle_add(app._open_prefs)

        t = threading.Thread(target=_ipc_loop, name="winclip-ipc", daemon=True)
        self._ipc_thread = t
        t.start()

    def _toggle_window(self) -> None:
        if self._window is None:
            self.activate()
            return
        if self._window.get_visible():
            self._window.hide()
        else:
            self._window.present()
            self._window.show_all()
            if isinstance(self._window, MainWindow):
                self._window.refresh_list()

    def _open_prefs(self) -> None:
        self.activate()
        if isinstance(self._window, MainWindow):
            self._window.show_preferences()

    def _on_activate(self, app: Gtk.Application) -> None:
        if self._window is None:
            self._window = MainWindow(
                application=app,
                db=self._db,
                settings=self._settings,
                on_settings_changed=self._reload_settings,
            )
        show_window = not self._start_hidden
        self._start_hidden = False
        if show_window:
            self._window.present()
            self._window.show_all()
        if self._open_prefs_on_launch and isinstance(self._window, MainWindow):
            self._window.show_preferences()
            self._open_prefs_on_launch = False
        if isinstance(self._window, MainWindow):
            self._window.refresh_list()
        self._ensure_hotkey()
        # Capture whatever is already on the clipboard when the app starts.
        GLib.timeout_add(400, self._poll_clipboard_once)

    def _poll_clipboard_once(self) -> None:
        self._poll_clipboard()
        return False

    def _reload_settings(self) -> None:
        self._settings = AppSettings.load()
        self._restart_hotkey()

    def _ensure_hotkey(self) -> None:
        if not self._settings.hotkey_enabled:
            self._stop_hotkey()
            return
        if self._hotkey_thread is not None and self._hotkey_thread.is_alive():
            return
        self._start_hotkey_thread()

    def _restart_hotkey(self) -> None:
        self._stop_hotkey()
        if self._settings.hotkey_enabled:
            self._start_hotkey_thread()

    def _start_hotkey_thread(self) -> None:
        app_ref = self

        def runner() -> None:
            try:
                from pynput import keyboard  # type: ignore[import-untyped]
            except ImportError:
                LOG.warning(
                    "Hotkey enabled but python3-pynput is not installed; "
                    f"install it or bind a shortcut to: {APP_COMMAND} --toggle"
                )
                return

            combo = app_ref._settings.hotkey_combo

            def on_activate() -> None:
                GLib.idle_add(app_ref._toggle_window)

            try:
                hotkey = keyboard.GlobalHotKeys({combo: on_activate})
            except Exception as exc:  # noqa: BLE001
                LOG.error("Invalid hotkey combo %r: %s", combo, exc)
                return
            app_ref._hotkey_listener = hotkey
            try:
                hotkey.run()
            except Exception as exc:  # noqa: BLE001
                LOG.error("Hotkey listener stopped: %s", exc)
            finally:
                app_ref._hotkey_listener = None

        t = threading.Thread(target=runner, name="winclip-hotkey", daemon=True)
        self._hotkey_thread = t
        t.start()

    def _stop_hotkey(self) -> None:
        h = self._hotkey_listener
        if h is not None:
            try:
                stop = getattr(h, "stop", None)
                if callable(stop):
                    stop()
            except Exception:  # noqa: BLE001
                pass
        self._hotkey_listener = None
        t = self._hotkey_thread
        self._hotkey_thread = None
        if t is not None and t.is_alive():
            t.join(timeout=1.0)

    def _on_clipboard_owner_change(
        self, _cb: Gtk.Clipboard, _event: Gdk.EventOwnerChange
    ) -> None:
        now = GLib.get_monotonic_time() // 1000
        if now < self._ignore_clipboard_until_ms:
            return
        if self._debounce_id:
            GLib.source_remove(self._debounce_id)
        self._debounce_id = GLib.timeout_add(
            self._settings.debounce_ms,
            self._poll_clipboard,
            priority=GLib.PRIORITY_DEFAULT,
        )

    def _poll_clipboard(self) -> bool:
        self._debounce_id = 0
        self._clipboard.request_targets(self._on_targets_ready, None)
        return False  # one-shot timeout; do not repeat

    def _on_targets_ready(self, clipboard: Gtk.Clipboard, *args) -> None:
        """GtkClipboardTargetsReceivedFunc: (clipboard, atoms, n_atoms, user_data)."""
        try:
            atoms: object | None = None
            n_atoms: object | None = None
            if len(args) >= 3:
                atoms, n_atoms, _user_data = args[0], args[1], args[2]
            elif len(args) == 2:
                a0, a1 = args
                if isinstance(a1, int):
                    atoms, n_atoms = a0, a1
                else:
                    atoms, n_atoms = a0, None
            elif len(args) == 1:
                atoms = args[0]
            else:
                LOG.debug("clipboard request_targets: unexpected arity %s", len(args))
                return

            atom_list = _gtk_clipboard_targets_to_atoms(atoms, n_atoms)
            if not atom_list:
                return
            names: set[str] = set()
            for a in atom_list:
                try:
                    nm = a.name()
                except Exception:  # noqa: BLE001
                    continue
                if nm:
                    names.add(nm)
            if not names:
                return
            if self._settings.store_images and (
                "image/png" in names or "image/bmp" in names or "image/jpeg" in names
            ):
                target = "image/png" if "image/png" in names else next(
                    n for n in ("image/jpeg", "image/bmp") if n in names
                )
                clipboard.request_contents(
                    Gdk.Atom.intern(target, False), self._on_image_contents, None
                )
                return
            if "text/uri-list" in names:
                clipboard.request_contents(
                    Gdk.Atom.intern("text/uri-list", False),
                    self._on_uri_contents,
                    None,
                )
                return
            if "x-special/gnome-copied-files" in names:
                clipboard.request_contents(
                    Gdk.Atom.intern("x-special/gnome-copied-files", False),
                    self._on_gnome_files_contents,
                    None,
                )
                return
            for t in (
                "UTF8_STRING",
                "text/plain;charset=utf-8",
                "text/plain",
                "STRING",
                "TEXT",
            ):
                if t in names:
                    clipboard.request_contents(
                        Gdk.Atom.intern(t, False), self._on_text_contents, None
                    )
                    return
        except Exception:  # noqa: BLE001
            LOG.exception("clipboard target handling failed")

    def _on_image_contents(
        self, _cb: Gtk.Clipboard, selection_data: Gtk.SelectionData, _data
    ) -> None:
        try:
            self._handle_image_contents(selection_data)
        except Exception:  # noqa: BLE001
            LOG.exception("clipboard image handling failed")

    def _handle_image_contents(self, selection_data: Gtk.SelectionData) -> None:
        if selection_data.get_length() <= 0:
            self._clipboard.request_targets(self._fallback_after_image, None)
            return
        pb = selection_data.get_pixbuf()
        raw = selection_data.get_data()
        path = app_images_dir() / f"img_{int(GLib.get_real_time())}.png"
        try:
            if pb is not None:
                pb.savev(str(path), "png", [], [])
            elif raw:
                path.write_bytes(raw)
            else:
                self._clipboard.request_targets(self._fallback_after_image, None)
                return
        except GLib.Error as exc:
            LOG.warning("Could not store image: %s", exc)
            return
        try:
            digest = stable_hash([path.read_bytes()])
        except OSError:
            return
        if self._db.exists_hash(digest):
            self._db.touch_hash(digest)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return
        thumb = write_thumbnail(path, 48, 32)
        self._db.insert(
            kind="image",
            title="Image",
            body=None,
            image_path=str(path),
            content_hash=digest,
            thumb_path=str(thumb) if thumb else None,
        )
        self._db.prune(self._settings.max_entries)
        self._emit_history_changed()

    def _fallback_after_image(self, clipboard: Gtk.Clipboard, *args) -> None:
        self._on_targets_ready(clipboard, *args)

    def _store_uri_paths(
        self, paths: list[str], truncated: bool, digest_source: str
    ) -> None:
        if not paths:
            return
        digest = stable_hash([digest_source.encode("utf-8", errors="replace")])
        if self._db.exists_hash(digest):
            self._db.touch_hash(digest)
            return
        n = len(paths)
        title = f"{n} file(s)" + (" (truncated)" if truncated else "")
        body = "\n".join(paths)
        self._db.insert(
            kind="uris",
            title=title,
            body=body,
            image_path=None,
            content_hash=digest,
        )
        self._db.prune(self._settings.max_entries)
        self._emit_history_changed()

    def _on_uri_contents(
        self, _cb: Gtk.Clipboard, selection_data: Gtk.SelectionData, _data
    ) -> None:
        try:
            if selection_data.get_length() < 0:
                return
            text = selection_data.get_text()
            if not text:
                return
            paths, truncated = parse_uri_list(
                text, self._settings.max_files_per_clip
            )
            self._store_uri_paths(paths, truncated, text)
        except Exception:  # noqa: BLE001
            LOG.exception("clipboard uri-list handling failed")

    def _on_gnome_files_contents(
        self, _cb: Gtk.Clipboard, selection_data: Gtk.SelectionData, _data
    ) -> None:
        try:
            if selection_data.get_length() < 0:
                return
            text = selection_data.get_text()
            if not text:
                return
            paths, truncated = parse_gnome_copied_files(
                text, self._settings.max_files_per_clip
            )
            self._store_uri_paths(paths, truncated, text)
        except Exception:  # noqa: BLE001
            LOG.exception("clipboard gnome-copied-files handling failed")

    def _on_text_contents(
        self, _cb: Gtk.Clipboard, selection_data: Gtk.SelectionData, _data
    ) -> None:
        try:
            if selection_data.get_length() < 0:
                return
            text = selection_data.get_text()
            if not text:
                return
            stripped = text.strip()
            if not stripped:
                return
            digest = stable_hash([stripped.encode("utf-8", errors="replace")])
            if self._db.exists_hash(digest):
                self._db.touch_hash(digest)
                return
            title = stripped.splitlines()[0][:120]
            self._db.insert(
                kind="text",
                title=title,
                body=text,
                image_path=None,
                content_hash=digest,
            )
            self._db.prune(self._settings.max_entries)
            self._emit_history_changed()
        except Exception:  # noqa: BLE001
            LOG.exception("clipboard text handling failed")

    def _emit_history_changed(self) -> None:
        if isinstance(self._window, MainWindow):
            GLib.idle_add(self._window.refresh_list)


class MainWindow(Gtk.ApplicationWindow):
    def __init__(
        self,
        *,
        application: Gtk.Application,
        db: Database,
        settings: AppSettings,
        on_settings_changed,
    ) -> None:
        super().__init__(application=application, title="Clipboard history")
        self.set_default_size(380, 500)
        self.set_border_width(0)
        self.connect("delete-event", self._on_delete_event)
        apply_winclip_theme(self)
        apply_window_icon(self)
        self._db = db
        self._settings = settings
        self._on_settings_changed = on_settings_changed
        self._app = application
        self._search_query = ""
        self._search_debounce_id = 0

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        style_widget(outer, "winclip-shell")

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        style_widget(header, "winclip-header")
        title_lbl = Gtk.Label(label="Clipboard history", xalign=0)
        style_widget(title_lbl, "winclip-title")
        header.pack_start(title_lbl, True, True, 0)

        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        for icon, tip, handler in (
            (
                theme_icon_name(
                    ["edit-clear-all-symbolic", "edit-clear-symbolic"],
                    "edit-clear-symbolic",
                ),
                "Clear unpinned",
                lambda _b: self._clear_unpinned(),
            ),
            (
                theme_icon_name(
                    ["preferences-desktop-keyboard-shortcuts-symbolic", "input-keyboard-symbolic"],
                    "input-keyboard-symbolic",
                ),
                "Shortcuts",
                lambda _b: self._open_preferences_dialog(),
            ),
            (
                theme_icon_name(["emblem-system-symbolic", "preferences-system-symbolic"], "preferences-system-symbolic"),
                "Settings",
                lambda _b: self._open_preferences_dialog(),
            ),
        ):
            btn = Gtk.Button()
            btn.set_relief(Gtk.ReliefStyle.NONE)
            style_widget(btn, "winclip-toolbtn")
            btn.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
            btn.set_tooltip_text(tip)
            btn.connect("clicked", handler)
            tools.pack_start(btn, False, False, 0)
        header.pack_start(tools, False, False, 0)
        outer.pack_start(header, False, False, 0)

        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search clipboard history")
        style_widget(self._search_entry, "winclip-search")
        self._search_entry.connect("search-changed", self._on_search_changed)
        self._search_entry.connect("stop-search", self._on_search_cleared)
        outer.pack_start(self._search_entry, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.NONE)
        style_widget(scrolled, "winclip-scroll")
        if hasattr(scrolled, "set_min_content_height"):
            scrolled.set_min_content_height(280)
        self._list = Gtk.ListBox()
        self._list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._list.set_activate_on_single_click(True)
        self._list.connect("row-activated", self._on_row_activated)
        style_widget(self._list, "winclip-list")
        scrolled.add(self._list)
        outer.pack_start(scrolled, True, True, 0)

        hint = Gtk.Label(
            label="Click an item to paste · Runs in tray when closed",
            xalign=0.5,
        )
        style_widget(hint, "winclip-footer")
        outer.pack_start(hint, False, False, 0)

        self.add(outer)
        self.refresh_list()
        self.show_all()

    def show_preferences(self) -> None:
        self._open_preferences_dialog()

    @staticmethod
    def _stop_list_row_activate(_widget: Gtk.Widget, event: Gdk.Event) -> bool:
        event.stop_propagation()
        return False

    def _on_delete_event(self, _widget: Gtk.Widget, _event: Gdk.Event) -> bool:
        """Close button hides the window; app keeps running in the tray."""
        self.hide()
        return True

    def _on_search_changed(self, _entry: Gtk.SearchEntry) -> None:
        if self._search_debounce_id:
            GLib.source_remove(self._search_debounce_id)
        self._search_debounce_id = GLib.timeout_add(150, self._apply_search_filter)

    def _apply_search_filter(self) -> bool:
        self._search_debounce_id = 0
        self._search_query = self._search_entry.get_text()
        self.refresh_list()
        return False

    def _on_search_cleared(self, entry: Gtk.SearchEntry) -> None:
        entry.set_text("")
        self._search_query = ""
        self.refresh_list()

    def refresh_list(self) -> None:
        for ch in list(self._list.get_children()):
            self._list.remove(ch)
        query = self._search_query.strip()
        if query:
            entries = self._db.search_entries(query, limit=500)
        else:
            entries = self._db.list_entries(limit=500)
        if not entries:
            row = Gtk.ListBoxRow()
            style_widget(row, "winclip-empty-row")
            row.set_selectable(False)
            row.set_sensitive(False)
            if query:
                msg = f'No clips match "{query}".'
            else:
                msg = (
                    "No clips yet. Copy text or files — they appear here automatically."
                )
            lbl = Gtk.Label(label=msg)
            lbl.set_line_wrap(True)
            lbl.set_margin_top(24)
            lbl.set_margin_bottom(24)
            lbl.set_margin_start(16)
            lbl.set_margin_end(16)
            lbl.set_xalign(0.5)
            style_widget(lbl, "winclip-empty")
            row.add(lbl)
            self._list.add(row)
            row.show_all()
        else:
            for entry in entries:
                row = self._make_row(entry)
                self._list.add(row)
        self._list.show_all()

    def _make_row(self, entry: ClipEntry) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        style_widget(row, "winclip-row")
        row.set_size_request(-1, _ROW_HEIGHT)
        setattr(row, "_winclip_id", entry.id)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        style_widget(hbox, "winclip-row-box")
        hbox.set_margin_top(6)
        hbox.set_margin_bottom(6)
        hbox.set_margin_start(10)
        hbox.set_margin_end(10)
        hbox.set_valign(Gtk.Align.CENTER)

        kind_icon = Gtk.Image.new_from_icon_name(
            _kind_icon_name(entry.kind), _ROW_ICON_SIZE
        )
        kind_icon.set_valign(Gtk.Align.CENTER)
        hbox.pack_start(kind_icon, False, False, 0)

        if entry.kind == "image":
            title_text = "Image (not pasted)"
        else:
            title_text = entry.title
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        text_box.set_valign(Gtk.Align.CENTER)
        title_lbl = Gtk.Label(label=title_text, xalign=0, yalign=0.5)
        title_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        title_lbl.set_single_line_mode(True)
        style_widget(title_lbl, "winclip-item-title")
        sub = Gtk.Label(label=f"{entry.kind} · #{entry.id}", xalign=0, yalign=0.5)
        sub.set_ellipsize(Pango.EllipsizeMode.END)
        sub.set_single_line_mode(True)
        style_widget(sub, "winclip-item-sub")
        text_box.pack_start(title_lbl, False, False, 0)
        text_box.pack_start(sub, False, False, 0)
        hbox.pack_start(text_box, True, True, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        actions.set_valign(Gtk.Align.CENTER)

        pin = self._make_pin_button(entry)
        delete = Gtk.Button.new_from_icon_name(
            "edit-delete-symbolic", Gtk.IconSize.BUTTON
        )
        delete.set_relief(Gtk.ReliefStyle.NONE)
        style_widget(delete, "winclip-delete")
        delete.set_valign(Gtk.Align.CENTER)
        delete.connect("clicked", self._on_delete_clicked, entry.id)
        for btn in (pin, delete):
            btn.connect("button-press-event", self._stop_list_row_activate)

        actions.pack_start(pin, False, False, 0)
        actions.pack_start(delete, False, False, 0)
        hbox.pack_start(actions, False, False, 0)

        row.add(hbox)
        row.show_all()
        return row

    def _make_pin_button(self, entry: ClipEntry) -> Gtk.ToggleButton:
        pin = Gtk.ToggleButton()
        pin.set_relief(Gtk.ReliefStyle.NONE)
        style_widget(pin, "winclip-pin")
        pin.set_valign(Gtk.Align.CENTER)
        icon = pin_icon_names(entry.pinned)
        pin.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
        pin.set_tooltip_text(
            "Unpin (kept when history rotates)" if entry.pinned else "Pin to keep in history"
        )
        pin_handler = pin.connect("toggled", self._on_pin_toggled, entry.id)
        pin.handler_block(pin_handler)
        pin.set_active(entry.pinned)
        pin.handler_unblock(pin_handler)
        return pin

    def _on_pin_toggled(self, btn: Gtk.ToggleButton, entry_id: int) -> None:
        if self._db.get(entry_id) is None:
            return
        active = btn.get_active()
        self._db.set_pinned(entry_id, active)
        img = btn.get_image()
        if isinstance(img, Gtk.Image):
            img.set_from_icon_name(pin_icon_names(active), Gtk.IconSize.BUTTON)
        btn.set_tooltip_text(
            "Unpin (kept when history rotates)" if active else "Pin to keep in history"
        )

    def _on_delete_clicked(self, _btn: Gtk.Button, entry_id: int) -> None:
        self._db.delete(entry_id)
        self.refresh_list()

    def _on_row_activated(self, _lb: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        entry_id = getattr(row, "_winclip_id", None)
        if entry_id is None:
            return
        self._apply_entry_to_clipboard(int(entry_id))

    def _apply_entry_to_clipboard(self, entry_id: int) -> None:
        entry = self._db.get(entry_id)
        if entry is None:
            return
        clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        if isinstance(self._app, WinclipApplication):
            ignore_ms = 900 if entry.kind == "image" else 450
            self._app.mark_ignore_clipboard(ignore_ms)

        try:
            if entry.kind == "text" and entry.body:
                clip.set_text(entry.body, -1)
            elif entry.kind == "uris" and entry.body:
                lines = [ln.strip() for ln in entry.body.splitlines() if ln.strip()]
                uris: list[str] = []
                for ln in lines:
                    try:
                        uris.append(Path(ln).expanduser().resolve().as_uri())
                    except (OSError, ValueError):
                        continue
                if not uris:
                    return

                targets = [Gtk.TargetEntry.new("text/uri-list", 0, 0)]

                def get_func(
                    _clipboard: Gtk.Clipboard,
                    selection_data: Gtk.SelectionData,
                    _info: int,
                    user_data,
                ) -> None:
                    selection_data.set_uris(user_data)

                def clear_func(_cb: Gtk.Clipboard, _user_data) -> None:
                    return

                clip.set_with_data(targets, get_func, clear_func, uris)
            elif entry.kind == "image":
                # Text-focused build: image clips are kept for reference only.
                return
        except GLib.Error as exc:
            LOG.warning("Clipboard write failed: %s", exc)
        GLib.idle_add(self.refresh_list)

    def _clear_unpinned(self) -> None:
        for e in self._db.list_entries():
            if not e.pinned:
                self._db.delete(e.id)
        self.refresh_list()

    def _open_preferences_dialog(self) -> None:
        s = AppSettings.load()
        dlg = Gtk.Dialog(
            title=f"{APP_DISPLAY_NAME} settings",
            transient_for=self,
            modal=True,
            destroy_with_parent=True,
        )
        dlg.add_buttons("_Cancel", Gtk.ResponseType.CANCEL, "_Save", Gtk.ResponseType.OK)
        dlg.set_default_size(480, 420)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=12)
        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        r = 0

        def spin_row(label: str, val: int, low: int, high: int) -> Gtk.SpinButton:
            nonlocal r
            lbl = Gtk.Label(label=label, xalign=0)
            adj = Gtk.Adjustment(value=val, lower=low, upper=high, step_increment=1)
            sp = Gtk.SpinButton.new(adj, 1, 0)
            grid.attach(lbl, 0, r, 1, 1)
            grid.attach(sp, 1, r, 1, 1)
            r += 1
            return sp

        sp_max = spin_row("Max history entries", s.max_entries, 20, 500)
        sp_files = spin_row("Max files per clip", s.max_files_per_clip, 1, 100)
        sp_debounce = spin_row("Debounce (ms)", s.debounce_ms, 50, 500)

        chk_img = Gtk.CheckButton(label="Store images")
        chk_img.set_active(s.store_images)
        grid.attach(chk_img, 0, r, 2, 1)
        r += 1

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        grid.attach(sep, 0, r, 2, 1)
        r += 1

        hot_title = Gtk.Label(label="<b>Keyboard shortcut</b>", xalign=0, use_markup=True)
        grid.attach(hot_title, 0, r, 2, 1)
        r += 1

        chk_hot = Gtk.CheckButton(
            label="Built-in global hotkey (install package: python3-pynput)"
        )
        chk_hot.set_active(s.hotkey_enabled)
        grid.attach(chk_hot, 0, r, 2, 1)
        r += 1

        ent_combo = Gtk.Entry()
        ent_combo.set_text(s.hotkey_combo)
        ent_combo.set_placeholder_text("<ctrl>+<alt>+v")
        hot_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hot_row.pack_start(ent_combo, True, True, 0)
        btn_record = Gtk.Button.new_with_label("Record…")
        hot_row.pack_start(btn_record, False, False, 0)
        grid.attach(hot_row, 0, r, 2, 1)
        r += 1

        preset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for label, combo in HOTKEY_PRESETS:
            btn = Gtk.Button.new_with_label(label)

            def _set_preset(_b: Gtk.Button, c: str = combo) -> None:
                ent_combo.set_text(c)

            btn.connect("clicked", _set_preset)
            preset_row.pack_start(btn, False, False, 0)
        grid.attach(preset_row, 0, r, 2, 1)
        r += 1

        shortcut_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_sys_kb = Gtk.Button.new_with_label("Open system keyboard settings")
        btn_help = Gtk.Button.new_with_label("Custom shortcut help")
        shortcut_btns.pack_start(btn_sys_kb, False, False, 0)
        shortcut_btns.pack_start(btn_help, False, False, 0)
        grid.attach(shortcut_btns, 0, r, 2, 1)
        r += 1

        hint = Gtk.Label(
            label=f"Command for desktop shortcuts: {APP_COMMAND} --toggle",
            xalign=0,
        )
        hint.get_style_context().add_class("dim-label")
        grid.attach(hint, 0, r, 2, 1)
        r += 1

        outer.pack_start(grid, False, False, 0)
        dlg.get_content_area().add(outer)

        def on_record(_btn: Gtk.Button) -> None:
            cap = HotkeyCaptureDialog(self, ent_combo.get_text().strip())
            cap.show_all()
            if cap.run() == Gtk.ResponseType.OK:
                captured = cap.get_captured_combo()
                if captured:
                    ent_combo.set_text(captured)
            cap.destroy()

        def on_sys_kb(_btn: Gtk.Button) -> None:
            if not try_open_system_keyboard_settings():
                open_shortcut_setup_help(self)

        btn_record.connect("clicked", on_record)
        btn_sys_kb.connect("clicked", on_sys_kb)
        btn_help.connect("clicked", lambda _b: open_shortcut_setup_help(self))

        dlg.show_all()
        resp = dlg.run()
        if resp == Gtk.ResponseType.OK:
            combo = ent_combo.get_text().strip() or s.hotkey_combo
            if chk_hot.get_active() and not validate_pynput_combo(combo):
                err = Gtk.MessageDialog(
                    transient_for=self,
                    modal=True,
                    destroy_with_parent=True,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Invalid keyboard shortcut",
                )
                err.format_secondary_text(
                    f"Could not parse {combo!r}.\n"
                    "Use Record… or a preset, or install python3-pynput."
                )
                err.run()
                err.destroy()
                dlg.destroy()
                return
            s.max_entries = int(sp_max.get_value_as_int())
            s.max_files_per_clip = int(sp_files.get_value_as_int())
            s.debounce_ms = int(sp_debounce.get_value_as_int())
            s.store_images = chk_img.get_active()
            s.hotkey_enabled = chk_hot.get_active()
            s.hotkey_combo = combo
            s.save()
            self._on_settings_changed()
        dlg.destroy()
