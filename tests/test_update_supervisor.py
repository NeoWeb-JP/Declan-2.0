from email.message import Message
from http_test_doubles import HTTPResponse
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import Mock, patch

import update_supervisor as supervisor


class HealthTests(TestCase):
    def test_health_requires_live_child_pid_and_valid_payload(self):
        child = Mock(pid=123)
        child.poll.return_value = None
        for pid, body, expected in (('123', b'{"status":"ok"}', True), ('456', b'{"status":"ok"}', False),
                                    ('123', b'invalid', False)):
            response = HTTPResponse(body)
            response.headers = Message()
            response.headers['X-Declan-Pid'] = pid
            opener = Mock()
            opener.open.return_value = response
            with patch.object(supervisor, 'monotonic', side_effect=[0, 1, 31]), patch.object(supervisor, 'sleep'):
                self.assertEqual(supervisor.healthy(opener, 1234, child), expected)
        child.poll.return_value = 1
        self.assertFalse(supervisor.healthy(Mock(), 1234, child))

    def test_stop_escalates_when_child_will_not_exit(self):
        import subprocess
        child = Mock()
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired('child', 5), 0]
        supervisor.stop(child)
        child.terminate.assert_called_once()
        child.kill.assert_called_once()


@skipUnless(os.name == 'posix', 'Linux deployment uses symbolic links')
class SupervisorTests(TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.new = self.root / 'releases' / 'new'
        self.old = self.root / 'releases' / 'old'
        for build in (self.new, self.old):
            build.mkdir(parents=True)
            (build / 'server.py').touch()
        (self.root / 'current').symlink_to(self.new)
        (self.root / 'previous').symlink_to(self.old)
        self.enterContext(patch.object(supervisor.signal, 'signal'))

    def test_bad_health_rolls_back_and_launches_previous(self):
        new, old = Mock(), Mock()
        new.poll.return_value = None
        old.wait.return_value = 0
        launch = Mock(side_effect=[new, old])
        with patch.object(supervisor, 'healthy', side_effect=[False, True]), patch.object(supervisor, 'prune_old'):
            self.assertEqual(supervisor.supervise(self.root, launch=launch), 0)
        self.assertEqual((self.root / 'current').resolve(), self.old)
        new.terminate.assert_called_once()
        self.assertEqual(launch.call_args_list[1].kwargs['cwd'], self.old)
        self.assertEqual(launch.call_args.kwargs['env']['DECLAN_UPDATE_SUPERVISED'], '1')

    def test_missing_executable_rolls_back_and_both_bad_builds_exit(self):
        with patch.object(supervisor, 'healthy', return_value=False):
            self.assertEqual(supervisor.supervise(self.root, launch=Mock(side_effect=OSError())), 1)
        self.assertEqual((self.root / 'current').resolve(), self.old)

    def test_restart_code_launches_new_selection_and_cleanup_failure_is_nonfatal(self):
        first, second = Mock(), Mock()
        first.wait.return_value = 75
        second.wait.return_value = 0
        with patch.object(supervisor, 'healthy', return_value=True), patch.object(
                supervisor, 'prune_old', side_effect=OSError()):
            self.assertEqual(supervisor.supervise(self.root, launch=Mock(side_effect=[first, second])), 0)

    def test_failed_rollback_and_cleanup_log_only_fixed_metadata(self):
        first, second = Mock(), Mock()
        first.poll.return_value = None
        second.wait.return_value = 0
        secret = "private-release-path-with-token"
        with patch.object(supervisor, "healthy", side_effect=[False, True]), \
             patch.object(supervisor, "prune_old", side_effect=OSError(secret)), \
             patch.object(supervisor, "_LOGGER") as logger:
            self.assertEqual(supervisor.supervise(
                self.root, launch=Mock(side_effect=[first, second])), 0)
        logger.warning.assert_any_call(
            "Selected release failed startup health check; rolling back")
        logger.warning.assert_any_call(
            "Release cleanup failed (reason=%s)", "OSError")
        self.assertNotIn(secret, repr(logger.warning.call_args_list))

    def test_prune_keeps_selected_previous_recent_and_external_symlink_targets(self):
        backups = self.new / '.data' / 'upgrade-backups'
        backups.mkdir(parents=True)
        for directory in (self.root / 'releases', backups):
            for i in range(6):
                entry = directory / f'extra-{i}'
                entry.mkdir()
                (entry / 'file').touch()
                os.utime(entry, (i, i))
        external = self.root / 'external'
        external.mkdir()
        (backups / 'link').symlink_to(external)
        supervisor.prune_old(self.root, self.new / '.data')
        self.assertTrue(self.new.exists())
        self.assertTrue(self.old.exists())
        self.assertTrue(external.exists())
        self.assertFalse((backups / 'extra-0').exists())
        self.assertTrue((backups / 'extra-5').exists())


@skipUnless(os.name == 'posix', 'Linux deployment uses symbolic links')
class EarlyCrashRollbackTests(TestCase):
    """A new release that is healthy at startup but crashes soon after goes back once."""

    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.new = self.root / 'releases' / 'new'
        self.old = self.root / 'releases' / 'old'
        for build in (self.new, self.old):
            build.mkdir(parents=True)
            (build / 'server.py').touch()
        (self.root / 'current').symlink_to(self.new)
        (self.root / 'previous').symlink_to(self.old)
        self.enterContext(patch.object(supervisor.signal, 'signal'))
        self.enterContext(patch.object(supervisor, 'healthy', return_value=True))
        self.enterContext(patch.object(supervisor, 'prune_old'))

    def child(self, code):
        child = Mock()
        child.wait.return_value = code
        return child

    def run_supervisor(self, children, clock):
        launch = Mock(side_effect=children)
        with patch.object(supervisor, 'monotonic', side_effect=clock):
            result = supervisor.supervise(self.root, launch=launch)
        return result, launch

    def test_early_crash_after_update_restart_rolls_back_once(self):
        # start -> exit 75 (update activated) -> new release crashes 10 s in -> previous runs
        result, launch = self.run_supervisor(
            [self.child(75), self.child(1), self.child(0)], [0, 5, 100, 110])
        self.assertEqual(result, 0)
        self.assertEqual((self.root / 'current').resolve(), self.old)
        self.assertEqual([call.kwargs['cwd'] for call in launch.call_args_list], [self.new, self.new, self.old])

    def test_previous_release_crashing_early_does_not_ping_pong(self):
        result, launch = self.run_supervisor(
            [self.child(75), self.child(1), self.child(2)], [0, 5, 100, 110, 200, 210])
        self.assertEqual(result, 2)
        self.assertEqual(launch.call_count, 3)

    def test_crash_on_first_start_is_not_rolled_back(self):
        result, launch = self.run_supervisor([self.child(1)], [0, 10])
        self.assertEqual(result, 1)
        self.assertEqual((self.root / 'current').resolve(), self.new)
        self.assertEqual(launch.call_count, 1)

    def test_late_crash_after_update_is_a_normal_failure(self):
        result, _ = self.run_supervisor([self.child(75), self.child(1)], [0, 5, 5 + supervisor.EARLY_CRASH_SECONDS])
        self.assertEqual(result, 1)
        self.assertEqual((self.root / 'current').resolve(), self.new)

    def test_clean_exit_is_never_rolled_back(self):
        result, _ = self.run_supervisor([self.child(75), self.child(0)], [0, 5, 100, 110])
        self.assertEqual(result, 0)
        self.assertEqual((self.root / 'current').resolve(), self.new)

    def test_missing_previous_release_returns_the_crash_code(self):
        (self.root / 'previous').unlink()
        result, launch = self.run_supervisor([self.child(75), self.child(3)], [0, 5, 100, 110])
        self.assertEqual(result, 3)
        self.assertEqual(launch.call_count, 2)
