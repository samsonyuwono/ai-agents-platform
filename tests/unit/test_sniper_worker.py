"""Unit tests for sniper_worker daemon."""

import signal
from unittest.mock import MagicMock, patch, call

import scripts.sniper_worker as worker


class TestSniperWorker:
    """Test sniper worker loop and signal handling."""

    def setup_method(self):
        """Reset shutdown flag before each test."""
        worker._shutdown = False

    def test_run_loop_calls_run_scheduled_jobs(self):
        """Worker loop calls run_scheduled_jobs on each iteration."""
        sniper = MagicMock()
        sniper._shutdown = False
        sniper.run_scheduled_jobs.return_value = {'jobs_run': 0, 'results': {}}

        call_count = 0

        def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                worker._shutdown = True

        with patch.object(worker.time, 'sleep', side_effect=fake_sleep):
            worker.run_loop(sniper, poll_seconds=1)

        sniper.run_scheduled_jobs.assert_called()

    def test_run_loop_sleeps_between_iterations(self):
        """Worker sleeps for the configured interval between iterations."""
        sniper = MagicMock()
        sniper._shutdown = False
        sniper.run_scheduled_jobs.return_value = {'jobs_run': 0, 'results': {}}

        sleep_calls = []

        def fake_sleep(seconds):
            sleep_calls.append(seconds)
            if len(sleep_calls) >= 3:
                worker._shutdown = True

        with patch.object(worker.time, 'sleep', side_effect=fake_sleep):
            worker.run_loop(sniper, poll_seconds=3)

        assert all(s == 1 for s in sleep_calls)
        assert len(sleep_calls) == 3

    def test_signal_handler_sets_shutdown_flag(self):
        """SIGTERM causes clean exit via shutdown flag."""
        assert worker._shutdown is False
        worker._handle_signal(signal.SIGTERM, None)
        assert worker._shutdown is True

    def test_sigint_sets_shutdown_flag(self):
        """SIGINT also sets shutdown flag."""
        worker._handle_signal(signal.SIGINT, None)
        assert worker._shutdown is True

    def test_shutdown_breaks_sleep_loop(self):
        """Setting shutdown during sleep causes early exit."""
        sniper = MagicMock()
        sniper._shutdown = False
        sniper.run_scheduled_jobs.return_value = {'jobs_run': 0, 'results': {}}

        call_count = 0

        def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            worker._shutdown = True

        with patch.object(worker.time, 'sleep', side_effect=fake_sleep):
            worker.run_loop(sniper, poll_seconds=60)

        assert call_count == 1

    def test_sniper_shutdown_breaks_loop(self):
        """Setting sniper._shutdown during sleep also exits the loop."""
        sniper = MagicMock()
        sniper._shutdown = False
        sniper.run_scheduled_jobs.return_value = {'jobs_run': 0, 'results': {}}

        call_count = 0

        def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            sniper._shutdown = True

        with patch.object(worker.time, 'sleep', side_effect=fake_sleep):
            worker.run_loop(sniper, poll_seconds=60)

        assert call_count == 1

    def test_get_poll_interval_default(self):
        """Default poll interval is 10 seconds."""
        import os
        env = os.environ.copy()
        env.pop('SNIPER_WORKER_POLL_SECONDS', None)
        with patch.dict('os.environ', env, clear=True):
            assert worker.get_poll_interval() == 10

    def test_get_poll_interval_from_env(self):
        """Poll interval is overridable via SNIPER_WORKER_POLL_SECONDS."""
        with patch.dict('os.environ', {'SNIPER_WORKER_POLL_SECONDS': '30'}):
            assert worker.get_poll_interval() == 30

    def test_run_loop_logs_job_results(self):
        """Worker logs results when jobs are run."""
        sniper = MagicMock()
        sniper._shutdown = False
        sniper.run_scheduled_jobs.return_value = {
            'jobs_run': 1,
            'results': {1: {'outcome': 'booked'}}
        }

        def fake_sleep(seconds):
            worker._shutdown = True

        with patch.object(worker.time, 'sleep', side_effect=fake_sleep):
            with patch.object(worker.logger, 'info') as mock_log:
                worker.run_loop(sniper, poll_seconds=1)

        log_messages = [c.args[0] for c in mock_log.call_args_list]
        assert any('Ran 1 job(s)' in msg for msg in log_messages)

    def test_run_loop_handles_exception(self):
        """Worker continues after an exception in run_scheduled_jobs."""
        sniper = MagicMock()
        sniper._shutdown = False
        call_count = 0

        def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient error")
            return {'jobs_run': 0, 'results': {}}

        sniper.run_scheduled_jobs.side_effect = side_effect

        sleep_count = 0

        def fake_sleep(seconds):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                worker._shutdown = True

        with patch.object(worker.time, 'sleep', side_effect=fake_sleep):
            worker.run_loop(sniper, poll_seconds=1)

        assert sniper.run_scheduled_jobs.call_count >= 2

    def test_clear_cookies_for_proxy(self):
        """Cookies are cleared when proxy is configured."""
        with patch('scripts.sniper_worker.Settings') as mock_settings:
            mock_settings.has_proxy_configured.return_value = True
            with patch('scripts.sniper_worker.Path') as mock_path:
                mock_cookie = MagicMock()
                mock_cookie.exists.return_value = True
                mock_path.home.return_value.__truediv__ = MagicMock(return_value=mock_cookie)
                worker._clear_cookies_for_proxy()
                mock_cookie.unlink.assert_called_once()

    def test_clear_cookies_skipped_without_proxy(self):
        """Cookies are not cleared when proxy is not configured."""
        with patch('scripts.sniper_worker.Settings') as mock_settings:
            mock_settings.has_proxy_configured.return_value = False
            with patch('scripts.sniper_worker.Path') as mock_path:
                worker._clear_cookies_for_proxy()
                mock_path.home.assert_not_called()

    def test_reset_stale_active_jobs(self):
        """Stale active jobs are reset to pending on startup."""
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 2
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_store = MagicMock()
        mock_store.conn = mock_conn
        mock_store.__enter__ = MagicMock(return_value=mock_store)
        mock_store.__exit__ = MagicMock(return_value=False)

        with patch('scripts.sniper_worker.ReservationStore', return_value=mock_store):
            worker._reset_stale_active_jobs()

        mock_cursor.execute.assert_called_once_with(
            "UPDATE sniper_jobs SET status = 'pending' WHERE status = 'active'"
        )
        mock_conn.commit.assert_called_once()
