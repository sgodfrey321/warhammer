#!/usr/bin/env python3
"""Starts the backend (uvicorn) and frontend (vite) dev servers together.

Usage:
    python dev.py                 # start both
    python dev.py --import-data   # re-run the bsdata-indexer import first

Ctrl+C stops both.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _lan_ip() -> str | None:
    """Best-effort local LAN IP for printing a reachable URL -- doesn't actually send
    anything (UDP connect on a socket never transmits a packet, just picks the outbound
    interface the OS would use). Returns None if there's no route out (fine, we just skip
    printing the LAN URL then)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
VENV_PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def stream_output(proc: subprocess.Popen, prefix: str) -> None:
    for line in proc.stdout:
        print(f"[{prefix}] {line}", end="")


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        # frontend runs via shell=True (npm.cmd needs a shell host on Windows), so
        # proc.terminate() would only kill the cmd.exe wrapper and orphan the real
        # node/vite process still holding the port -- taskkill /T kills the whole tree.
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--import-data",
        action="store_true",
        help="Re-run scripts.import_unit_definitions before starting (safe to re-run, upserts).",
    )
    args = parser.parse_args()

    if not VENV_PYTHON.exists():
        sys.exit(f"venv python not found at {VENV_PYTHON} -- see backend/README.md setup")
    if not (FRONTEND_DIR / "node_modules").exists():
        sys.exit(f"{FRONTEND_DIR / 'node_modules'} missing -- run `npm install` in frontend/ first")

    if args.import_data:
        subprocess.run(
            [str(VENV_PYTHON), "-m", "scripts.import_unit_definitions"], cwd=BACKEND_DIR, check=True
        )

    backend = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "uvicorn", "app.main:app",  "--host", "0.0.0.0"],
        cwd=BACKEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    # npm resolves to npm.cmd on Windows, which Python can only launch through a shell.
    frontend = subprocess.Popen(
        "npm run dev",
        cwd=FRONTEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        shell=True,
    )

    for proc, prefix in ((backend, "backend"), (frontend, "frontend")):
        threading.Thread(target=stream_output, args=(proc, prefix), daemon=True).start()

    print("backend:  http://localhost:8000")
    print("frontend: http://localhost:5173  (or 5174 if 5173 was taken -- watch the [frontend] log line)")
    lan_ip = _lan_ip()
    if lan_ip:
        print(f"\nAlso reachable from other machines on your LAN at: http://{lan_ip}:5173")
    print("Ctrl+C to stop both.\n")

    try:
        while True:
            if backend.poll() is not None:
                print(f"\n[backend] exited unexpectedly (code {backend.returncode})")
                break
            if frontend.poll() is not None:
                print(f"\n[frontend] exited unexpectedly (code {frontend.returncode})")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nStopping...")
        for proc in (backend, frontend):
            _kill_tree(proc)


if __name__ == "__main__":
    main()
