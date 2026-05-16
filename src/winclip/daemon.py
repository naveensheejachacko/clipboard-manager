from __future__ import annotations

import os
import sys


def maybe_detach_from_terminal(argv: list[str]) -> None:
    """
    If started from an interactive terminal, fork into the background so closing
    the terminal does not kill Winclip (same idea as CopyQ / Clipman).
    """
    if os.environ.get("WINCLIP_DETACHED") == "1":
        return
    if any(
        flag in argv
        for flag in ("--toggle", "--prefs", "--preferences", "--foreground")
    ):
        return
    # Autostart / desktop launcher: usually no controlling terminal.
    if not sys.stdin.isatty():
        return

    from winclip.paths import log_path

    pid = os.fork()
    if pid > 0:
        print(
            "Clipboard Manager is running in the background (check the tray icon). "
            "You can close this terminal.",
            file=sys.stderr,
        )
        raise SystemExit(0)

    os.setsid()
    pid2 = os.fork()
    if pid2 > 0:
        raise SystemExit(0)

    os.environ["WINCLIP_DETACHED"] = "1"
    os.chdir(os.path.expanduser("~"))

    log_file = log_path()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_fd = open(log_file, "a", encoding="utf-8")
    devnull = open(os.devnull, "r")
    os.dup2(devnull.fileno(), sys.stdin.fileno())
    os.dup2(log_fd.fileno(), sys.stdout.fileno())
    os.dup2(log_fd.fileno(), sys.stderr.fileno())
