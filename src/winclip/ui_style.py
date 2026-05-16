from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, Gtk

# Windows 11–style dark clipboard panel (frosted overlay).
_WINCLIP_CSS = """
.winclip-window {
  background-color: rgba(32, 32, 36, 0.90);
  color: #f3f3f3;
  border-radius: 10px;
}

.winclip-shell {
  background-color: transparent;
}

.winclip-header {
  background-color: transparent;
  padding: 12px 14px 4px 14px;
}

.winclip-title {
  font-size: 15px;
  font-weight: 600;
  color: #ffffff;
}

.winclip-toolbtn {
  background-color: transparent;
  border: none;
  border-radius: 6px;
  padding: 6px;
  min-width: 32px;
  min-height: 32px;
}

.winclip-toolbtn:hover {
  background-color: rgba(255, 255, 255, 0.10);
}

.winclip-search {
  margin: 4px 12px 8px 12px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background-color: rgba(0, 0, 0, 0.25);
  color: #f3f3f3;
}

.winclip-search:focus {
  border-color: rgba(96, 165, 250, 0.85);
  box-shadow: none;
}

.winclip-scroll {
  background-color: transparent;
  border: none;
}

.winclip-list {
  background-color: transparent;
  color: #f3f3f3;
}

.winclip-list row {
  background-color: transparent;
  border: none;
  padding: 0;
  margin: 2px 8px;
}

.winclip-list row:hover {
  background-color: rgba(255, 255, 255, 0.07);
}

.winclip-list row:selected {
  background-color: rgba(0, 103, 192, 0.55);
}

.winclip-row-box {
  background-color: transparent;
}

.winclip-item-title {
  font-size: 13px;
  font-weight: 500;
  color: #f3f3f3;
}

.winclip-item-sub {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.50);
}

.winclip-pin {
  background-color: transparent;
  border: none;
  padding: 4px;
}

.winclip-pin:hover {
  background-color: rgba(255, 255, 255, 0.08);
  border-radius: 6px;
}

.winclip-pin:checked {
  color: #60a5fa;
}

.winclip-delete {
  background-color: transparent;
  border: none;
  padding: 4px;
  opacity: 0.75;
}

.winclip-delete:hover {
  background-color: rgba(255, 80, 80, 0.25);
  border-radius: 6px;
  opacity: 1;
}

.winclip-footer {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.40);
  padding: 6px 14px 10px 14px;
}

.winclip-empty {
  color: rgba(255, 255, 255, 0.55);
  font-size: 13px;
}
"""


def configure_transparent_window(window: Gtk.Window) -> None:
    screen = window.get_screen()
    if screen is None:
        return
    visual = screen.get_rgba_visual()
    if visual is not None and screen.is_composited():
        window.set_visual(visual)
    window.set_app_paintable(True)


def apply_winclip_theme(window: Gtk.Window) -> None:
    configure_transparent_window(window)
    provider = Gtk.CssProvider()
    provider.load_from_data(_WINCLIP_CSS.encode("utf-8"))
    Gtk.StyleContext.add_provider(
        window.get_style_context(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    window.get_style_context().add_class("winclip-window")


def style_widget(widget: Gtk.Widget, class_name: str) -> None:
    widget.get_style_context().add_class(class_name)
