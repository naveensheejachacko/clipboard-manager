# Clipboard Manager

Lightweight **clipboard history** for **Linux Mint, Ubuntu, and Debian**. Search old copies, pin important clips, run in the **system tray**, and open history with a keyboard shortcut (similar to **Windows Win+V**).

![GTK3](https://img.shields.io/badge/GTK-3-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Linux-lightgrey)

## Features

- Clipboard **history** for text and file paths (`text/uri-list`)
- **Search** across history
- **Pin** items so they are not rotated out
- **Tray icon** — closing the window keeps the app running
- Optional **global shortcut** (`clipboard-manager --toggle`)
- Dark, semi-transparent UI inspired by Windows 11 clipboard history

## Requirements

- Linux with **GTK 3** and a **compositor** (transparency; Cinnamon on Mint is fine)
- **Python 3.10+**
- Packages (installed automatically with the `.deb`):

  ```text
  python3-gi gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0
  ```

Optional:

- `gir1.2-ayatanaappindicator3-0.1` — tray icon on Mint/Ubuntu
- `python3-pynput` — built-in global hotkey in Settings

---

## Install from GitHub (recommended)

Use a **Release** `.deb` — no need to clone the repo on your PC.

### 1. Download the latest release

1. Open [clipboard-manager releases](https://github.com/naveensheejachacko/clipboard-manager/releases/latest).
2. Download **`clipboard-manager_*_all.deb`** (for example `clipboard-manager_0.2.0_all.deb`).

Or from a terminal:

```bash
cd ~/Downloads
wget https://github.com/naveensheejachacko/clipboard-manager/releases/download/v0.2.0/clipboard-manager_0.2.0_all.deb
```

### 2. Install the package

```bash
cd ~/Downloads
sudo apt install ./clipboard-manager_0.2.0_all.deb
```

`apt` will install dependencies. If you see a lock error, wait until **Update Manager** / **Software Manager** finishes, then retry.

### 3. Start the app

```bash
clipboard-manager --tray
```

You can close the terminal — the app stays in the **tray**.

### 4. First-time setup (recommended)

| Step | Action |
|------|--------|
| **Autostart** | *Menu → Startup Applications* → Add → Command: `clipboard-manager --tray` |
| **Shortcut** | *Settings → Keyboard → Shortcuts → Custom* → Command: `clipboard-manager --toggle` → e.g. **Ctrl+Alt+V** or **Super+V** |
| **Launch** | Application menu → search **Clipboard Manager** |

Legacy command: `winclip` is a symlink to `clipboard-manager` (old installs).

### 5. Verify

```bash
clipboard-manager --toggle   # should show/hide the history window
```

Logs: `~/.local/share/winclip/winclip.log`

---

## Publish a release on GitHub (for maintainers)

If you are uploading the app for others to download:

```bash
git clone https://github.com/naveensheejachacko/clipboard-manager.git
cd clipboard-manager
chmod +x scripts/build-deb.sh
./scripts/build-deb.sh
```

This creates:

```text
dist/clipboard-manager_0.2.0_all.deb
```

On GitHub:

1. **Releases** → **Draft a new release**
2. Tag: `v0.2.0` (match `version` in `pyproject.toml`)
3. Title: `Clipboard Manager 0.2.0`
4. Attach **`dist/clipboard-manager_0.2.0_all.deb`**
5. Publish release

Users then follow [Install from GitHub](#install-from-github-recommended) above.

---

## Install from source (developers)

```bash
git clone https://github.com/naveensheejachacko/clipboard-manager.git
cd clipboard-manager
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0 \
  gir1.2-ayatanaappindicator3-0.1 python3-pynput fakeroot
chmod +x scripts/build-deb.sh
./scripts/build-deb.sh
sudo apt install ./dist/clipboard-manager_*_all.deb
```

Run without installing:

```bash
PYTHONPATH=src clipboard-manager --tray
```

---

## Usage

| Action | How |
|--------|-----|
| Open / hide history | `clipboard-manager --toggle` or your custom shortcut |
| Copy from history | **Click** a row (text and file paths) |
| Pin | Pin icon on the row |
| Search | Search box at the top |
| Settings | Gear / keyboard icons in the header |
| Quit completely | Tray icon → **Quit Clipboard Manager** |

Closing the window (**X**) only hides it; the app keeps running in the tray.

### Data locations

| Path | Purpose |
|------|---------|
| `~/.local/share/winclip/` | History database and logs |
| `~/.config/winclip/settings.json` | Settings |

---

## Uninstall

```bash
sudo apt remove clipboard-manager
```

Optional — remove saved history:

```bash
rm -rf ~/.local/share/winclip ~/.config/winclip
```

---

## Troubleshooting

**`apt` waits for cache lock**  
Close **Update Manager** / **Software Manager**, or wait until it finishes.

**No tray icon**  
```bash
sudo apt install gir1.2-ayatanaappindicator3-0.1
```

**Shortcut stops after closing terminal**  
Start with `clipboard-manager --tray` (not plain `clipboard-manager` in a terminal you close), or enable **Startup Applications**.

**Transparency looks solid**  
Normal without a compositor; the dark theme still applies.

**Upgrading from old `winclip` package**  
```bash
sudo apt remove winclip
sudo apt install ./clipboard-manager_0.2.0_all.deb
```

---

## License

[MIT](LICENSE)
