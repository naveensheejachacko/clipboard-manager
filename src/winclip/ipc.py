from __future__ import annotations

import logging
import socket
from pathlib import Path

from winclip.paths import ipc_socket_path

LOG = logging.getLogger(__name__)


def try_send_command(command: str, timeout_s: float = 0.35) -> bool:
    """If the main Winclip instance is listening, send a one-line command and return True."""
    path = ipc_socket_path()
    try:
        if not path.is_socket():
            return False
    except OSError:
        return False
    line = (command.strip().upper() + "\n").encode("ascii", errors="ignore")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout_s)
            s.connect(str(path))
            s.sendall(line)
    except OSError as exc:
        LOG.debug("IPC send %r failed: %s", command, exc)
        return False
    return True
