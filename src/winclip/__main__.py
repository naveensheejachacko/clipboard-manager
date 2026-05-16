from __future__ import annotations

import logging
import os
import sys

from winclip.app import WinclipApplication
from winclip.daemon import maybe_detach_from_terminal
from winclip.ipc import try_send_command

# Gtk.Application does not know these; strip them before app.run().
_WINCLIP_ONLY_FLAGS = frozenset(
    {
        "--tray",
        "--background",
        "--toggle",
        "--prefs",
        "--preferences",
        "--foreground",
    }
)


def _gtk_argv() -> list[str]:
    return [sys.argv[0], *[a for a in sys.argv[1:] if a not in _WINCLIP_ONLY_FLAGS]]


def _setup_logging() -> None:
    from winclip.paths import log_path

    log_file = log_path()
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    try:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass
    if os.environ.get("WINCLIP_DETACHED") != "1":
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        root.addHandler(sh)


def main() -> None:
    argv = sys.argv[1:]
    maybe_detach_from_terminal(argv)

    _setup_logging()
    if "--toggle" in argv and try_send_command("TOGGLE"):
        raise SystemExit(0)
    want_prefs = "--prefs" in argv or "--preferences" in argv
    if want_prefs and try_send_command("PREFS"):
        raise SystemExit(0)

    start_hidden = "--tray" in argv or "--background" in argv

    app = WinclipApplication()
    app.set_open_prefs_on_launch(want_prefs)
    app.set_start_hidden(start_hidden)
    exit_code = app.run(_gtk_argv())
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
