"""
Browser Worker Manager — singleton that manages a persistent browser worker process.

Starts the worker on first use, sends commands via stdin/stdout JSON protocol,
and falls back to one-shot subprocess if the worker is unavailable.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
from typing import Dict, Optional

from config.settings import Settings

logger = logging.getLogger(__name__)

# Path to worker and one-shot scripts
_WORKER_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "browser_worker.py"
)
_ONESHOT_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "browser_search.py"
)


class BrowserWorkerManager:
    """Thread-safe singleton that manages a persistent browser worker process."""

    _instance: Optional['BrowserWorkerManager'] = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._cmd_counter = 0
        self._ready = False

    @classmethod
    def get_instance(cls) -> 'BrowserWorkerManager':
        """Get or create the singleton instance (thread-safe)."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def send_command(self, method: str, args: Dict, timeout: int = 180,
                     resy_credentials: Optional[Dict] = None) -> Dict:
        """Send a command to the worker and return the response.

        Falls back to one-shot subprocess if the worker is unavailable.

        Args:
            method: Method name (e.g. 'search_venues', 'search_by_cuisine')
            args: Arguments dict to pass to the method
            timeout: Max seconds to wait for a response
            resy_credentials: Optional user credentials for subprocess env

        Returns:
            Result dict with 'success' key
        """
        with self._lock:
            try:
                self._ensure_worker_running(resy_credentials)
            except Exception as e:
                logger.warning("Worker startup failed, falling back to one-shot: %s", e)
                return self._oneshot_fallback(method, args, resy_credentials)

            if not self._ready or self._process is None:
                logger.warning("Worker not ready, falling back to one-shot")
                return self._oneshot_fallback(method, args, resy_credentials)

            self._cmd_counter += 1
            cmd_id = str(self._cmd_counter)

            cmd = {"id": cmd_id, "method": method, "args": args}

            try:
                # Write command to worker stdin
                self._process.stdin.write(json.dumps(cmd) + "\n")
                self._process.stdin.flush()

                # Read response (with timeout)
                response = self._read_response(cmd_id, timeout)
                if response is None:
                    logger.warning("Worker timed out, killing and falling back")
                    self._kill_worker()
                    return self._oneshot_fallback(method, args, resy_credentials)

                return response

            except (BrokenPipeError, OSError) as e:
                logger.warning("Worker pipe broken: %s, falling back", e)
                self._kill_worker()
                return self._oneshot_fallback(method, args, resy_credentials)

    def _ensure_worker_running(self, resy_credentials: Optional[Dict] = None):
        """Start the worker if it's not running."""
        if self._process is not None and self._process.poll() is None:
            return  # Still running

        # Worker is dead or never started
        self._ready = False
        self._start_worker(resy_credentials)

    def _start_worker(self, resy_credentials: Optional[Dict] = None):
        """Spawn the worker subprocess and wait for 'ready' signal."""
        logger.info("Starting browser worker process...")

        env = os.environ.copy()
        if resy_credentials:
            env["RESY_EMAIL"] = resy_credentials.get("email", "")
            env["RESY_PASSWORD"] = resy_credentials.get("password", "")

        self._process = subprocess.Popen(
            [sys.executable, _WORKER_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            bufsize=1,  # Line-buffered
        )

        # Wait for "ready" signal
        startup_timeout = Settings.RESY_BROWSER_WORKER_STARTUP_TIMEOUT
        response = self._read_response(None, startup_timeout)

        if response is None:
            self._kill_worker()
            raise RuntimeError("Worker failed to start within timeout")

        if response.get("status") == "ready":
            self._ready = True
            logger.info("Browser worker is ready")
        elif response.get("status") == "error":
            self._kill_worker()
            raise RuntimeError(f"Worker startup error: {response.get('error')}")
        else:
            self._kill_worker()
            raise RuntimeError(f"Unexpected worker startup response: {response}")

    def _read_response(self, expected_id: Optional[str], timeout: float) -> Optional[Dict]:
        """Read a JSON response line from the worker stdout.

        Args:
            expected_id: If set, keep reading until we get a response with this id.
                        If None, return the first valid JSON line (for startup).
            timeout: Max seconds to wait.

        Returns:
            Parsed dict or None on timeout.
        """
        if self._process is None or self._process.stdout is None:
            return None

        deadline = time.time() + timeout

        while time.time() < deadline:
            # Check if process is still alive
            if self._process.poll() is not None:
                logger.warning("Worker process exited with code %s", self._process.returncode)
                return None

            # Use select-like polling via threading to avoid blocking forever
            import selectors
            sel = selectors.DefaultSelector()
            sel.register(self._process.stdout, selectors.EVENT_READ)
            remaining = deadline - time.time()
            if remaining <= 0:
                sel.close()
                return None

            events = sel.select(timeout=min(remaining, 1.0))
            sel.close()

            if not events:
                continue

            line = self._process.stdout.readline()
            if not line:
                # EOF
                return None

            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Non-JSON line from worker: %s", line[:200])
                continue

            # If we're waiting for startup (no expected_id), return any response
            if expected_id is None:
                return data

            # Check if this is our response
            if data.get("id") == expected_id:
                return data

            # Could be an out-of-band status message (idle_shutdown, fatal)
            if data.get("status") in ("idle_shutdown", "fatal"):
                logger.warning("Worker status: %s", data.get("status"))
                self._ready = False
                return None

        return None  # Timeout

    def _kill_worker(self):
        """Kill the worker process."""
        self._ready = False
        if self._process is not None:
            try:
                self._process.kill()
                self._process.wait(timeout=5)
            except Exception:
                pass
            self._process = None

    def _oneshot_fallback(self, method: str, args: Dict,
                          resy_credentials: Optional[Dict] = None) -> Dict:
        """Fall back to one-shot browser_search.py subprocess."""
        logger.info("Using one-shot fallback for: %s", method)
        try:
            env = os.environ.copy()
            if resy_credentials:
                env["RESY_EMAIL"] = resy_credentials.get("email", "")
                env["RESY_PASSWORD"] = resy_credentials.get("password", "")

            result = subprocess.run(
                [sys.executable, _ONESHOT_SCRIPT, method, json.dumps(args)],
                capture_output=True, text=True, timeout=300,
                env=env,
            )
            stdout = result.stdout.strip()
            if not stdout:
                return {"success": False, "error": f"One-shot returned no output. stderr: {result.stderr[-300:] if result.stderr else '(empty)'}"}
            return json.loads(stdout)
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "One-shot browser search timed out"}
        except json.JSONDecodeError:
            return {"success": False, "error": f"Failed to parse one-shot output"}
        except Exception as e:
            return {"success": False, "error": f"One-shot fallback failed: {e}"}

    def shutdown(self):
        """Gracefully shut down the worker."""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                try:
                    cmd = {"id": "shutdown", "method": "shutdown", "args": {}}
                    self._process.stdin.write(json.dumps(cmd) + "\n")
                    self._process.stdin.flush()
                    self._process.wait(timeout=10)
                except Exception:
                    self._kill_worker()
            self._process = None
            self._ready = False

    def is_ready(self) -> bool:
        """Check if the worker is running and ready."""
        return (
            self._ready
            and self._process is not None
            and self._process.poll() is None
        )

    @classmethod
    def reset_instance(cls):
        """Reset the singleton (for testing)."""
        with cls._instance_lock:
            if cls._instance is not None:
                cls._instance.shutdown()
                cls._instance = None
