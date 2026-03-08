#!/usr/bin/env python3
"""
Export Resy Session — authenticate on laptop and upload session to VPS.

Launches a headful browser so you can solve CAPTCHA if needed, then exports
Playwright storage state (cookies + localStorage) and optionally SCPs it to
the VPS for the sniper worker.

Usage:
  python3 scripts/export_resy_session.py           # Export + auto-upload to VPS
  python3 scripts/export_resy_session.py --local    # Export only, no upload
"""

import argparse
import logging
import os
import subprocess
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from config.settings import Settings
from utils.resy_browser_client import ResyBrowserClient

logger = logging.getLogger(__name__)

STORAGE_STATE_FILE = Path.home() / '.resy_storage_state.json'


def export_session() -> Path:
    """Launch headful browser, authenticate, and export storage state.

    Returns:
        Path to the exported storage state file.
    """
    print("Launching headful browser for Resy login...")

    client = ResyBrowserClient(headless=False)
    try:
        client._launch_browser()
        client._login()

        if not client.is_authenticated:
            print("Login failed — cannot export session.")
            sys.exit(1)

        # Save full storage state (cookies + localStorage)
        client._save_session()
        print(f"Session exported to {STORAGE_STATE_FILE}")
        return STORAGE_STATE_FILE
    finally:
        client._cleanup()


def upload_to_vps(local_path: Path):
    """SCP storage state to VPS and restart sniper service."""
    remote_host = Settings.SNIPER_REMOTE_HOST
    if not remote_host:
        print("SNIPER_REMOTE_HOST not configured in .env — skipping upload.")
        print(f"Manually copy {local_path} to the VPS at ~/.resy_storage_state.json")
        return

    remote_path = f"{remote_host}:~/.resy_storage_state.json"
    print(f"Uploading to {remote_path}...")

    try:
        subprocess.run(
            ["scp", str(local_path), remote_path],
            check=True,
        )
        print("Upload complete.")
    except subprocess.CalledProcessError as e:
        print(f"SCP failed: {e}")
        print(f"Manually copy {local_path} to the VPS at ~/.resy_storage_state.json")
        return

    # Restart sniper service
    print("Restarting sniper service...")
    try:
        subprocess.run(
            ["ssh", remote_host, "systemctl restart sniper"],
            check=True,
        )
        print("Sniper service restarted.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to restart sniper: {e}")
        print(f"Manually run: ssh {remote_host} 'systemctl restart sniper'")


def main():
    parser = argparse.ArgumentParser(
        description="Export Resy session and upload to VPS",
    )
    parser.add_argument(
        "--local", action="store_true",
        help="Export only, do not upload to VPS",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    session_path = export_session()

    if not args.local:
        upload_to_vps(session_path)
    else:
        print("Local-only mode — skipping VPS upload.")


if __name__ == "__main__":
    main()
