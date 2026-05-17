from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gtk

# Solid dark panel — readable on any compositor / Mint theme (no see-through rows).
_WINCLIP_CSS = """
.winclip-window {
  background-color: #1e1e22;
  color: #ececec;
}

.winclip-shell {
  background-color: #1e1e22;
}

.winclip-header {
  background-color: #252528;
  padding: 14px 16px 12px 16px;
  border-bottom: 1px solid #3a3a40;
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
  color: #d8d8d8;
}

.winclip-toolbtn:hover {
  background-color: #3a3a42;
}

.winclip-search {
  margin: 10px 14px 8px 14px;
  padding: 9px 12px;
  border-radius: 8px;
  border: 1px solid #45454d;
  background-color: #2b2b30;
  color: #f0f0f0;
  caret-color: #60a5fa;
}

.winclip-search:focus {
  border-color: #3b82f6;
  background-color: #323238;
  box-shadow: none;
}

.winclip-scroll {
  background-color: #1e1e22;
  border: none;
}

.winclip-list {
  background-color: #1e1e22;
  color: #ececec;
}

.winclip-list row {
  background-color: #2a2a2f;
  border: 1px solid #38383f;
  border-radius: 8px;
  padding: 0;
  margin: 5px 12px;
  min-height: 58px;
  transition: background-color 120ms ease-out;
}

.winclip-list row:hover {
  background-color: #34343b;
  border-color: #4a4a54;
}

.winclip-list row:selected {
  background-color: #0b5cab;
  border-color: #1d7ad4;
}

.winclip-list row:selected .winclip-item-title,
.winclip-list row:selected .winclip-item-sub {
  color: #ffffff;
}

.winclip-row-box {
  background-color: transparent;
  padding: 8px 6px 8px 4px;
}

.winclip-item-title {
  font-size: 13px;
  font-weight: 500;
  color: #f2f2f2;
}

.winclip-item-sub {
  font-size: 11px;
  color: #a8a8b0;
  margin-top: 2px;
}

.winclip-pin {
  background-color: transparent;
  border: none;
  padding: 4px;
  color: #c8c8d0;
}

.winclip-pin:hover {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 6px;
}

.winclip-pin:checked {
  color: #93c5fd;
}

.winclip-list row:selected .winclip-pin {
  color: #e8f0ff;
}

.winclip-delete {
  background-color: transparent;
  border: none;
  padding: 4px;
  color: #c8c8d0;
  opacity: 0.9;
}

.winclip-delete:hover {
  background-color: rgba(220, 60, 60, 0.35);
  border-radius: 6px;
  color: #ffffff;
  opacity: 1;
}

.winclip-footer {
  font-size: 11px;
  color: #8a8a94;
  padding: 8px 14px 12px 14px;
  background-color: #252528;
  border-top: 1px solid #3a3a40;
}

.winclip-empty {
  color: #9a9aa4;
  font-size: 13px;
  padding: 24px 16px;
}

.winclip-list row.winclip-empty-row {
  background-color: transparent;
  border: none;
  margin: 0;
  min-height: 0;
}
"""


def _prefer_dark_gtk_theme() -> None:
    settings = Gtk.Settings.get_default()
    if settings is None:
        return
    if hasattr(settings, "set_property"):
        try:
            settings.set_property("gtk-application-prefer-dark-theme", True)
        except (TypeError, AttributeError):
            pass


def apply_winclip_theme(window: Gtk.Window) -> None:
    """Apply opaque dark theme; avoids RGBA window so list text stays readable."""
    _prefer_dark_gtk_theme()
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
