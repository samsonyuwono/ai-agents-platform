"""Tests for BrowserWorkerManager."""

import json
import subprocess
import threading
import time

import pytest
from unittest.mock import patch, MagicMock, PropertyMock


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before and after each test."""
    from utils.browser_worker_manager import BrowserWorkerManager
    BrowserWorkerManager._instance = None
    yield
    BrowserWorkerManager._instance = None


class TestGetInstance:
    """Test singleton pattern."""

    def test_returns_same_instance(self):
        from utils.browser_worker_manager import BrowserWorkerManager
        a = BrowserWorkerManager.get_instance()
        b = BrowserWorkerManager.get_instance()
        assert a is b

    def test_thread_safe(self):
        """Multiple threads should get the same instance."""
        from utils.browser_worker_manager import BrowserWorkerManager
        instances = []

        def get():
            instances.append(BrowserWorkerManager.get_instance())

        threads = [threading.Thread(target=get) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(inst is instances[0] for inst in instances)


class TestSendCommand:
    """Test send_command with mocked worker process."""

    def test_send_command_success(self):
        """Successful command through the worker."""
        from utils.browser_worker_manager import BrowserWorkerManager
        manager = BrowserWorkerManager.get_instance()

        # Pre-set worker as running so _ensure_worker_running is a no-op
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        manager._process = mock_proc
        manager._ready = True

        expected = {"id": "1", "success": True, "results": [{"name": "Test"}]}
        with patch.object(manager, '_read_response', return_value=expected):
            result = manager.send_command("search_venues", {"query": "Test"}, timeout=5)

        assert result["success"] is True
        assert result["results"] == [{"name": "Test"}]
        # Verify command was written to stdin
        mock_proc.stdin.write.assert_called_once()
        written = json.loads(mock_proc.stdin.write.call_args[0][0])
        assert written["method"] == "search_venues"

    def test_send_command_worker_timeout_falls_back(self):
        """If worker times out, falls back to one-shot."""
        from utils.browser_worker_manager import BrowserWorkerManager
        manager = BrowserWorkerManager.get_instance()

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        manager._process = mock_proc
        manager._ready = True

        with patch.object(manager, '_read_response', return_value=None), \
             patch.object(manager, '_oneshot_fallback', return_value={"success": True, "results": []}) as mock_fb:
            result = manager.send_command("search_venues", {"query": "Test"}, timeout=5)
            mock_fb.assert_called_once()
            assert result["success"] is True

    @patch('utils.browser_worker_manager.subprocess.Popen')
    @patch('utils.browser_worker_manager.Settings')
    def test_send_command_worker_startup_fails_falls_back(self, mock_settings, mock_popen):
        """If worker fails to start, falls back to one-shot."""
        mock_settings.RESY_BROWSER_WORKER_STARTUP_TIMEOUT = 1
        mock_settings.RESY_BROWSER_WORKER_IDLE_TIMEOUT = 1800

        # Worker exits immediately
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # Exited
        mock_proc.stdout.readline.return_value = ""
        mock_proc.stdout.fileno = MagicMock(return_value=99)
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()
        mock_popen.return_value = mock_proc

        from utils.browser_worker_manager import BrowserWorkerManager
        manager = BrowserWorkerManager.get_instance()

        # Mock the one-shot fallback
        with patch.object(manager, '_oneshot_fallback', return_value={"success": True, "results": []}) as mock_fallback:
            result = manager.send_command("search_venues", {"query": "Test"}, timeout=5)
            mock_fallback.assert_called_once()
            assert result["success"] is True


class TestOneshotFallback:
    """Test one-shot fallback mechanism."""

    @patch('utils.browser_worker_manager.subprocess.run')
    def test_oneshot_success(self, mock_run):
        """One-shot fallback returns parsed JSON."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"success": True, "results": [{"name": "Carbone"}]}) + "\n",
            stderr="",
        )

        from utils.browser_worker_manager import BrowserWorkerManager
        manager = BrowserWorkerManager()
        result = manager._oneshot_fallback("search_venues", {"query": "Carbone"})

        assert result["success"] is True
        assert result["results"][0]["name"] == "Carbone"

    @patch('utils.browser_worker_manager.subprocess.run')
    def test_oneshot_timeout(self, mock_run):
        """One-shot returns error on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=300)

        from utils.browser_worker_manager import BrowserWorkerManager
        manager = BrowserWorkerManager()
        result = manager._oneshot_fallback("search_venues", {"query": "Test"})

        assert result["success"] is False
        assert "timed out" in result["error"]

    @patch('utils.browser_worker_manager.subprocess.run')
    def test_oneshot_empty_output(self, mock_run):
        """One-shot returns error when no output."""
        mock_run.return_value = MagicMock(stdout="", stderr="some error")

        from utils.browser_worker_manager import BrowserWorkerManager
        manager = BrowserWorkerManager()
        result = manager._oneshot_fallback("search_venues", {"query": "Test"})

        assert result["success"] is False
        assert "no output" in result["error"].lower()

    @patch('utils.browser_worker_manager.subprocess.run')
    def test_oneshot_passes_credentials(self, mock_run):
        """Credentials are passed via environment."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"success": True, "results": []}) + "\n",
            stderr="",
        )

        from utils.browser_worker_manager import BrowserWorkerManager
        manager = BrowserWorkerManager()
        creds = {"email": "test@example.com", "password": "pass123"}
        manager._oneshot_fallback("search_venues", {"query": "Test"}, resy_credentials=creds)

        call_kwargs = mock_run.call_args
        env = call_kwargs.kwargs.get("env") or call_kwargs[1].get("env")
        assert env["RESY_EMAIL"] == "test@example.com"
        assert env["RESY_PASSWORD"] == "pass123"


class TestShutdown:
    """Test shutdown behavior."""

    def test_shutdown_no_process(self):
        """Shutdown is safe when no worker is running."""
        from utils.browser_worker_manager import BrowserWorkerManager
        manager = BrowserWorkerManager()
        manager.shutdown()  # Should not raise

    @patch('utils.browser_worker_manager.subprocess.Popen')
    def test_shutdown_sends_command(self, mock_popen):
        """Shutdown sends shutdown command to worker."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.wait = MagicMock()
        mock_popen.return_value = mock_proc

        from utils.browser_worker_manager import BrowserWorkerManager
        manager = BrowserWorkerManager()
        manager._process = mock_proc
        manager._ready = True

        manager.shutdown()

        # Should have written shutdown command
        mock_proc.stdin.write.assert_called_once()
        written = mock_proc.stdin.write.call_args[0][0]
        cmd = json.loads(written)
        assert cmd["method"] == "shutdown"
        assert manager._ready is False


class TestIsReady:
    """Test is_ready check."""

    def test_not_ready_initially(self):
        from utils.browser_worker_manager import BrowserWorkerManager
        manager = BrowserWorkerManager()
        assert manager.is_ready() is False

    def test_ready_with_running_process(self):
        from utils.browser_worker_manager import BrowserWorkerManager
        manager = BrowserWorkerManager()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        manager._process = mock_proc
        manager._ready = True
        assert manager.is_ready() is True

    def test_not_ready_if_process_dead(self):
        from utils.browser_worker_manager import BrowserWorkerManager
        manager = BrowserWorkerManager()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # Exited
        manager._process = mock_proc
        manager._ready = True
        assert manager.is_ready() is False


class TestResetInstance:
    """Test reset_instance for testing."""

    def test_reset_clears_singleton(self):
        from utils.browser_worker_manager import BrowserWorkerManager
        inst = BrowserWorkerManager.get_instance()
        assert BrowserWorkerManager._instance is inst
        BrowserWorkerManager.reset_instance()
        assert BrowserWorkerManager._instance is None
