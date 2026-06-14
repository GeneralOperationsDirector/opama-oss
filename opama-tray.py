#!/usr/bin/env python3
"""
opama system tray icon for Linux (AppIndicator3/Ayatana).

Mirrors the pattern used by openclaw-tray.py.
Controls the Docker Compose stack and shows live health status.

Dependencies (Ubuntu):
    sudo apt install python3-gi python3-pil gir1.2-ayatanaappindicator3-0.1
    # fallback: gir1.2-appindicator3-0.1
"""
import subprocess
import threading
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

import gi
gi.require_version("Gtk", "3.0")
try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator3
except ValueError:
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3

from gi.repository import GLib, Gtk
from PIL import Image, ImageDraw, ImageFont

OPAMA_DIR    = Path(__file__).parent
ICON_RUNNING = "/tmp/opama-tray-running.png"
ICON_STOPPED = "/tmp/opama-tray-stopped.png"
DASHBOARD    = "http://localhost:5173"
API_DOCS     = "http://localhost:6000/docs"
HEALTHZ      = "http://localhost:6000/healthz"
POLL_INTERVAL = 8  # seconds


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def _api_healthy() -> bool:
    try:
        with urlopen(HEALTHZ, timeout=3) as r:
            return r.status == 200
    except (URLError, OSError):
        return False


def _compose_running() -> bool:
    """True if at least one opama container is running."""
    try:
        out = subprocess.check_output(
            ["docker", "compose", "ps", "--services", "--filter", "status=running"],
            cwd=str(OPAMA_DIR), text=True, timeout=5, stderr=subprocess.DEVNULL,
        )
        return bool(out.strip())
    except Exception:
        return False


def get_status() -> tuple[str, bool]:
    """Returns (label, is_healthy)."""
    if _api_healthy():
        return "Running", True
    if _compose_running():
        return "Starting…", False
    return "Stopped", False


# ---------------------------------------------------------------------------
# Icon generation
# ---------------------------------------------------------------------------

def _render_icon(running: bool, dest: str) -> None:
    """Render an opama icon with a green/red status dot."""
    size = 32
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background circle — indigo
    bg = (99, 102, 241, 255)
    draw.ellipse([0, 0, size - 1, size - 1], fill=bg)

    # "op" text centred
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
    except OSError:
        font = ImageFont.load_default()

    text = "op"
    bb = draw.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    draw.text(((size - tw) / 2 - 1, (size - th) / 2 - 2), text, font=font, fill=(255, 255, 255, 255))

    # Status dot (bottom-right)
    dot_color = (52, 211, 153, 255) if running else (239, 68, 68, 255)
    draw.ellipse([22, 22, 31, 31], fill=dot_color, outline=(0, 0, 0, 160))

    img.save(dest)


def build_icons() -> None:
    _render_icon(True,  ICON_RUNNING)
    _render_icon(False, ICON_STOPPED)


# ---------------------------------------------------------------------------
# Docker Compose helpers
# ---------------------------------------------------------------------------

def _compose(args: list[str]) -> None:
    subprocess.run(
        ["docker", "compose"] + args,
        cwd=str(OPAMA_DIR),
        timeout=120,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def start_stack()   -> None: _compose(["up", "-d"])
def stop_stack()    -> None: _compose(["down"])
def restart_stack() -> None: stop_stack(); start_stack()

def backup_db() -> None:
    backup_dir = OPAMA_DIR / "backups"
    backup_dir.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / f"opama-backup-{ts}.sql"
    try:
        with dest.open("w") as f:
            subprocess.run(
                ["docker", "compose", "exec", "-T", "postgres",
                 "pg_dump", "-U", "opama_user", "opama_dev"],
                cwd=str(OPAMA_DIR), stdout=f, timeout=60,
                stderr=subprocess.DEVNULL, check=True,
            )
        # Prune to 10 most recent
        backups = sorted(backup_dir.glob("*.sql"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[10:]:
            old.unlink()
    except Exception as e:
        _notify("opama backup failed", str(e))


def _notify(title: str, body: str) -> None:
    try:
        subprocess.run(["notify-send", title, body], timeout=5)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tray application
# ---------------------------------------------------------------------------

class OpamaTray:
    def __init__(self):
        build_icons()
        self._label, self._running = get_status()

        self.indicator = AppIndicator3.Indicator.new(
            "opama-tray",
            ICON_RUNNING if self._running else ICON_STOPPED,
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self._build_menu())

    def _build_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        # Title
        title = Gtk.MenuItem(label="opama")
        title.set_sensitive(False)
        menu.append(title)

        # Status
        self._status_item = Gtk.MenuItem(label=f"Status: {self._label}")
        self._status_item.set_sensitive(False)
        menu.append(self._status_item)

        menu.append(Gtk.SeparatorMenuItem())

        # Open links
        dash_item = Gtk.MenuItem(label="Open Dashboard")
        dash_item.connect("activate", lambda _: webbrowser.open(DASHBOARD))
        menu.append(dash_item)

        docs_item = Gtk.MenuItem(label="Open API Docs")
        docs_item.connect("activate", lambda _: webbrowser.open(API_DOCS))
        menu.append(docs_item)

        menu.append(Gtk.SeparatorMenuItem())

        # Service controls
        for label, action in [("Start", "start"), ("Stop", "stop"), ("Restart", "restart")]:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _, a=action: self._action(a))
            menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())

        backup_item = Gtk.MenuItem(label="Back Up Database")
        backup_item.connect("activate", lambda _: self._action("backup"))
        menu.append(backup_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit tray")
        quit_item.connect("activate", self._quit)
        menu.append(quit_item)

        menu.show_all()
        return menu

    # ── Actions ───────────────────────────────────────────────────────────────

    def _action(self, cmd: str) -> None:
        threading.Thread(target=self._run_action, args=(cmd,), daemon=True).start()

    def _run_action(self, cmd: str) -> None:
        GLib.idle_add(self._set_status, f"{cmd.capitalize()}ing…", None)
        if cmd == "start":
            start_stack()
        elif cmd == "stop":
            stop_stack()
        elif cmd == "restart":
            restart_stack()
        elif cmd == "backup":
            GLib.idle_add(self._set_status, "Backing up…", None)
            backup_db()
            _notify("opama", "Database backup saved to ./backups/")
        time.sleep(2)
        label, running = get_status()
        GLib.idle_add(self._set_status, label, running)

    def _set_status(self, label: str, running) -> None:
        self._label = label
        self._status_item.set_label(f"Status: {label}")
        if running is not None:
            self._running = running
            self.indicator.set_icon_full(
                ICON_RUNNING if running else ICON_STOPPED, label
            )

    # ── Polling ───────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        while True:
            time.sleep(POLL_INTERVAL)
            label, running = get_status()
            GLib.idle_add(self._set_status, label, running)

    def _quit(self, _) -> None:
        Gtk.main_quit()

    def run(self) -> None:
        threading.Thread(target=self._poll, daemon=True).start()
        Gtk.main()


if __name__ == "__main__":
    OpamaTray().run()
