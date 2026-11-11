"""Publication is a one-place release operation; installation still pins code identity."""
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase, skipUnless
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import updates


def release(tag, **changes):
    return {'tag_name': tag, 'draft': False, 'prerelease': False,
            'published_at': '2026-11-11T11:00:00Z', **changes}


class PublishedReleaseTests(TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {'DECLAN_UPDATE_SUPERVISED': '1'}, clear=True))
        self.enterContext(patch.object(updates, '_tags', {}))
        self.enterContext(patch.object(updates, '_job', {'state': 'idle'}))

    def test_default_lists_published_stable_releases_without_local_approval(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps([
            release('0.8.0'), release('0.10.0'), release('0.9.0'), release('0.11.0', draft=True),
            release('0.12.0', prerelease=True), release('0.13.0-rc.1'), release('../unsafe'),
            release('0.14.0', published_at=None), release('0.15.0', draft=None),
            release('0.16.0', prerelease=None), release('v0.10.1'),
        ]).encode())
        refs = '\n'.join(f"{'a'*40}\trefs/tags/{tag}" for tag in
                         ('0.8.0', '0.9.0', '0.10.0', '0.11.0', '0.12.0', '0.13.0-rc.1', 'v0.10.1', '0.99.0'))
        with patch.object(updates, 'layout', return_value=Path('/unused')), patch.object(
                updates, 'run', return_value=refs), patch.object(updates, 'build_opener', return_value=opener), patch.object(
                updates, 'trusted_releases', side_effect=AssertionError('No manual pins in the default channel')):
            self.assertEqual(updates.check(), ['v0.10.1', '0.10.0', '0.9.0', '0.8.0'])
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, updates.RELEASES_API)
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 10)
        self.assertEqual(updates._tags['0.10.0'], {'ref': 'a'*40, 'commit': 'a'*40, 'source': 'github'})
        self.assertIsNone(updates.NoRedirect().redirect_request(None, None, None, None, None, None))

    def test_annotated_tags_pin_object_and_peeled_commit_and_sort_numerically(self):
        refs = f"{'a'*40}\trefs/tags/0.10.0\n{'b'*40}\trefs/tags/0.10.0^{{}}\n{'c'*40}\trefs/tags/0.9.0\ninvalid\trefs/tags/0.20.0"
        with patch.object(updates, 'published_tags', return_value={'0.10.0', '0.9.0', '0.20.0'}), patch.object(
                updates, 'run', return_value=refs), patch.object(updates, 'layout', return_value=Path('/unused')):
            self.assertEqual(updates.check(), ['0.10.0', '0.9.0'])
            self.assertEqual(updates._tags['0.10.0']['commit'], 'b'*40)
            self.assertEqual(updates._tags['0.10.0']['ref'], 'a'*40)
            with patch.object(updates, 'Thread') as thread:
                updates.queue('0.10.0', '0.9.0')
                selection = thread.call_args.kwargs['args'][2]
                self.assertEqual(selection, updates._tags['0.10.0'])
                self.assertIsNot(selection, updates._tags['0.10.0'])

    def test_failed_checks_remove_previous_choices_and_no_layout_offers_nothing(self):
        updates._tags['0.10.0'] = {'ref': 'a'*40, 'commit': 'a'*40, 'source': 'github'}
        with patch.object(updates, 'layout', return_value=Path('/unused')), patch.object(
                updates, 'available_releases', side_effect=OSError('Rate limited')):
            with self.assertRaises(OSError):
                updates.check()
            with self.assertRaises(ValueError):
                updates.queue('0.10.0', '0.9.0')
        self.assertEqual(updates._tags, {})
        with patch.object(updates, 'layout', return_value=None):
            self.assertEqual(updates.check(), [])

    def test_changed_withdrawn_or_source_switched_release_never_clones(self):
        selection = {'ref': 'a'*40, 'commit': 'b'*40, 'source': 'github'}
        for catalog in ({}, {'0.10.0': {**selection, 'ref': 'c'*40}},
                        {'0.10.0': {**selection, 'commit': 'c'*40}}):
            with patch.object(updates, 'available_releases', return_value=catalog), patch.object(updates, 'run') as run:
                updates.install(Path('/unused'), '0.10.0', selection)
                run.assert_not_called()
                self.assertEqual(updates._job['state'], 'failed')
        with patch.dict(os.environ, {'DECLAN_UPDATE_SOURCE': 'pinned'}), patch.object(updates, 'run') as run:
            updates.install(Path('/unused'), '0.10.0', selection)
            run.assert_not_called()

    def test_invalid_selection_and_unsupervised_install_never_fetch_or_run(self):
        with patch.object(updates, 'run') as run, patch.object(updates, 'available_releases') as catalog:
            for selection in ('a'*40, {}, {'ref': 'bad', 'commit': 'b'*40, 'source': 'github'},
                              {'ref': 'a'*40, 'commit': 'b'*40, 'source': 'github', 'extra': True}):
                updates.install(Path('/unused'), '0.10.0', selection)
            updates.install(Path('/unused'), '../bad', {})
            with patch.dict(os.environ, {'DECLAN_UPDATE_SUPERVISED': ''}):
                updates.install(Path('/unused'), '0.10.0', {})
            run.assert_not_called()
            catalog.assert_not_called()

    def test_bad_metadata_redirects_and_http_errors_offer_no_fallback(self):
        for payload in (b'{}', b'[null]', b'broken json', b'x'*(updates.MAX_RELEASE_BYTES+1)):
            opener = Mock()
            opener.open.return_value = io.BytesIO(payload)
            with patch.object(updates, 'build_opener', return_value=opener), self.assertRaises(OSError):
                updates.published_tags()
        opener = Mock()
        for code in (302, 403, 429, 500):
            opener.open.side_effect = HTTPError('url', code, 'Unavailable', {}, None)
            with patch.object(updates, 'build_opener', return_value=opener), self.assertRaises(OSError):
                updates.published_tags()
        with patch.dict(os.environ, {'DECLAN_UPDATE_SOURCE': 'unknown'}), self.assertRaises(ValueError):
            updates.release_source()

    def test_pinned_mode_remains_explicit_and_filters_mismatched_commits(self):
        refs = f"{'a'*40}\trefs/tags/0.10.0\n{'b'*40}\trefs/tags/0.9.0"
        with patch.dict(os.environ, {'DECLAN_UPDATE_SOURCE': 'pinned'}), patch.object(updates, 'trusted_releases',
                return_value={'0.10.0': 'a'*40, '0.9.0': 'c'*40}), patch.object(updates, 'run', return_value=refs), patch.object(
                updates, 'published_tags', side_effect=AssertionError('Pinned mode does not trust publication')):
            self.assertEqual(set(updates.available_releases()), {'0.10.0'})

    @skipUnless(os.name == 'posix', 'Production activation uses Linux symlinks')
    def test_published_annotated_release_installs_only_the_selected_commit(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / 'baseline'
            (app / '.data').mkdir(parents=True)
            (root / 'releases').mkdir()
            (root / 'current').symlink_to(app)
            selection = {'ref': 'a'*40, 'commit': 'b'*40, 'source': 'github'}
            restart = Event()
            def command(*args, **kwargs):
                if args[:2] == ('git', 'rev-parse'):
                    return 'a'*40 if args[-1] == 'refs/tags/0.10.0' else 'b'*40
                return ''
            with patch.object(updates, 'APP', app), patch.object(updates, 'layout', return_value=root), patch.object(
                    updates, 'RESTART', restart), patch.object(updates, 'available_releases', return_value={'0.10.0': selection}), patch.object(
                    updates, 'run', side_effect=command) as run:
                updates.install(root, '0.10.0', selection)
                self.assertEqual(updates._job['state'], 'restarting')
                self.assertTrue(restart.is_set())
                self.assertEqual((root / 'current' / '.declan-release').read_text().strip(), '0.10.0')
                self.assertEqual((root / 'previous').resolve(), app)
                self.assertEqual((root / 'current' / '.data').resolve(), app / '.data')
                self.assertTrue(any('venv' in call.args for call in run.call_args_list))

    @skipUnless(os.name == 'posix', 'Production staging uses Linux symlinks')
    def test_tag_moved_during_clone_never_executes_release(self):
        selection = {'ref': 'a'*40, 'commit': 'b'*40, 'source': 'github'}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'releases').mkdir()
            with patch.object(updates, 'available_releases', return_value={'0.10.0': selection}), patch.object(
                    updates, 'run', return_value='c'*40) as run:
                updates.install(root, '0.10.0', selection)
                self.assertFalse(any('venv' in call.args or 'pip' in call.args or 'server.py' in call.args
                                     for call in run.call_args_list))
                self.assertFalse(list((root / 'releases').iterdir()))
