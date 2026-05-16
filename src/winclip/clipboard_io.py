from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

LOG = logging.getLogger(__name__)


def _pump_gtk_clipboard_events(iterations: int = 8) -> None:
    """Let GTK/X11 finish registering clipboard ownership before the user pastes."""
    for _ in range(iterations):
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        context = GLib.MainContext.default()
        if context is not None:
            context.iteration(False)


def _set_image_via_xclip(path: Path) -> bool:
    xclip = shutil.which("xclip")
    if not xclip or not os.environ.get("DISPLAY"):
        return False
    try:
        subprocess.run(
            [xclip, "-selection", "clipboard", "-t", "image/png", "-i", str(path)],
            check=True,
            timeout=8,
            capture_output=True,
        )
        LOG.info("Clipboard image set via xclip: %s", path.name)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        LOG.warning("xclip image copy failed: %s", exc)
        return False


def _set_image_via_wl_copy(path: Path) -> bool:
    wl_copy = shutil.which("wl-copy")
    if not wl_copy or not os.environ.get("WAYLAND_DISPLAY"):
        return False
    try:
        with path.open("rb") as fh:
            subprocess.run(
                [wl_copy, "--type", "image/png"],
                stdin=fh,
                check=True,
                timeout=8,
                capture_output=True,
            )
        LOG.info("Clipboard image set via wl-copy: %s", path.name)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        LOG.warning("wl-copy image copy failed: %s", exc)
        return False


def _set_image_via_gtk(clipboard: Gtk.Clipboard, path: Path) -> bool:
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file(str(path))
    except GLib.Error as exc:
        LOG.warning("Could not load image for clipboard: %s", exc)
        return False

    # Synchronous set — replaces clipboard immediately (unlike lazy set_with_data).
    try:
        clipboard.set_image(pb, None)
        _pump_gtk_clipboard_events()
    except GLib.Error as exc:
        LOG.warning("gtk set_image failed: %s", exc)
        return False

    ok, png_bytes = pb.save_to_bufferv("png", [], [])
    if not ok or not png_bytes:
        LOG.info("Clipboard image set via GTK pixbuf: %s", path.name)
        return True

    targets = [Gtk.TargetEntry.new("image/png", 0, 0)]

    def get_func(
        _clipboard: Gtk.Clipboard,
        selection_data: Gtk.SelectionData,
        _info: int,
        user_data: bytes,
    ) -> None:
        selection_data.set("image/png", 8, user_data)

    def clear_func(_clipboard: Gtk.Clipboard, _user_data: object) -> None:
        return

    try:
        if clipboard.set_with_data(targets, get_func, clear_func, png_bytes):
            _pump_gtk_clipboard_events()
            LOG.info("Clipboard image set via GTK image/png: %s", path.name)
            return True
    except (GLib.Error, TypeError) as exc:
        LOG.debug("GTK image/png target skipped: %s", exc)

    LOG.info("Clipboard image set via GTK pixbuf only: %s", path.name)
    return True


def set_clipboard_image(clipboard: Gtk.Clipboard, image_path: Path) -> bool:
    """
    Put an image on the CLIPBOARD selection, replacing prior text.
    Prefer xclip/wl-copy on Linux (works reliably on Cinnamon/X11).
    """
    path = image_path.expanduser()
    if not path.is_file():
        LOG.warning("Image file missing: %s", path)
        return False

    if os.environ.get("WAYLAND_DISPLAY"):
        if _set_image_via_wl_copy(path):
            return True
    elif _set_image_via_xclip(path):
        return True

    return _set_image_via_gtk(clipboard, path)


def write_thumbnail(source_path: Path, max_w: int = 48, max_h: int = 32) -> Path | None:
    """Write a small PNG preview next to the full image for the history list."""
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            str(source_path), max_w, max_h, True
        )
        thumb = source_path.parent / f"{source_path.stem}_thumb.png"
        pb.savev(str(thumb), "png", [], [])
        return thumb
    except GLib.Error as exc:
        LOG.debug("Thumbnail not created for %s: %s", source_path, exc)
        return None
