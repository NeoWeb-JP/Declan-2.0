"""2.13.0/2.13.1-rc1 wrote the conversations database inside the release folder."""
from contextlib import closing
import os
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from declan.core import data_location_repair, diagnostics, history

ROOT = Path(__file__).resolve().parents[1]


def make_database(path, *, phrases=(), turns=(), budget=None, settings=None):
    with patch.object(history, "DATABASE", path):
        history.initialize()
        for phrase, target in phrases:
            history.teach_phrase(phrase, target)
        for message in turns:
            history.record("s", "assist", message, "ok")
        with history.database() as db:
            if budget is not None:
                db.execute("CREATE TABLE IF NOT EXISTS ai_budget (month TEXT PRIMARY KEY, reserved INTEGER NOT NULL)")
                db.execute("INSERT INTO ai_budget VALUES (?, ?)", budget)
            if settings is not None:
                db.execute("CREATE TABLE IF NOT EXISTS server_settings (key TEXT PRIMARY KEY, value TEXT)")
                db.execute("INSERT INTO server_settings VALUES ('guest', ?)", (settings,))


def rows(path, query):
    with closing(sqlite3.connect(path)) as db:
        return db.execute(query).fetchall()


class PathTests(unittest.TestCase):
    def test_databases_live_in_the_shared_repository_data_folder(self):
        self.assertEqual(history.DATABASE, ROOT / ".data" / "conversations.sqlite3")
        self.assertEqual(diagnostics.DATABASE, ROOT / ".data" / "diagnostics.sqlite3")

    def test_every_data_path_in_a_package_points_at_the_repository_root(self):
        pattern = re.compile(r"Path\(__file__\)\.resolve\(\)\.(parent\b|parents\[(\d+)\])\s*/\s*['\"]\.data['\"]")
        offenders = []
        for path in (ROOT / "declan").rglob("*.py"):
            depth = len(path.relative_to(ROOT).parts)  # parents[depth - 1] is the repository root
            for match in pattern.finditer(path.read_text(encoding="utf-8")):
                levels = 1 if match.group(1) == "parent" else int(match.group(2)) + 1
                if levels != depth:
                    offenders.append(f"{path.relative_to(ROOT)}: {match.group(0)}")
        self.assertEqual(offenders, [])


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        shared = self.root / "data"
        shared.mkdir()
        self.old_release = self.root / "releases" / "2.13.1-rc1-abc"
        self.app = self.root / "releases" / "2.13.2-rc1-def"
        for release in (self.old_release, self.app):
            release.mkdir(parents=True)
            (release / ".data").symlink_to(shared, target_is_directory=True)
        (self.root / "previous").symlink_to(self.old_release, target_is_directory=True)
        (self.root / "current").symlink_to(self.app, target_is_directory=True)
        self.target = self.app / ".data" / "conversations.sqlite3"
        self.stray = self.old_release / "declan" / "core" / ".data" / "conversations.sqlite3"

    def test_post_upgrade_work_is_merged_and_settings_are_left_for_review(self):
        make_database(self.target, phrases=[("lights please", "turn on the lounge lights"),
                                            ("bed time", "turn off the bedroom lights")],
                      turns=["before upgrade"], budget=("2026-11", 100), settings="input_boolean.guest")
        make_database(self.stray, phrases=[("bed time", "start bed time"), ("tunes", "play rock everywhere")],
                      turns=["after upgrade"], budget=("2026-11", 40), settings="default")
        logger = Mock()
        reports = data_location_repair.repair(self.app, self.target, logger=logger, now=lambda: 1700)

        self.assertEqual(len(reports), 1)
        self.assertEqual(dict(rows(self.target, "SELECT phrase, target FROM learned_intents")), {
            "lights please": "turn on the lounge lights",  # kept
            "bed time": "start bed time",                  # re-taught on 2.13 wins
            "tunes": "play rock everywhere",               # taught on 2.13
        })
        self.assertEqual(sorted(m for (m,) in rows(self.target, "SELECT message FROM turns")),
                         ["after upgrade", "before upgrade"])
        self.assertEqual(rows(self.target, "SELECT reserved FROM ai_budget"), [(140,)])
        # Settings are never overwritten with release-local copies.
        self.assertEqual(rows(self.target, "SELECT value FROM server_settings"), [("input_boolean.guest",)])
        self.assertEqual(reports[0]["not_merged"], {"server_settings": 1})
        self.assertFalse(self.stray.exists())
        self.assertTrue(Path(reports[0]["kept_as"]).exists())
        logger.warning.assert_called_once()

    def test_running_again_changes_nothing(self):
        make_database(self.target, phrases=[("a b", "turn on the lounge lights")])
        make_database(self.stray, turns=["after upgrade"])
        data_location_repair.repair(self.app, self.target)
        before = rows(self.target, "SELECT message FROM turns")
        self.assertEqual(data_location_repair.repair(self.app, self.target), [])
        self.assertEqual(rows(self.target, "SELECT message FROM turns"), before)

    def test_missing_shared_database_is_restored_from_the_release_copy(self):
        make_database(self.stray, phrases=[("tunes", "play rock everywhere")])
        reports = data_location_repair.repair(self.app, self.target)
        self.assertTrue(reports[0]["copied"])
        self.assertEqual(rows(self.target, "SELECT phrase FROM learned_intents"), [("tunes",)])

    def test_in_place_install_and_unreadable_files_are_handled(self):
        make_database(self.target, phrases=[("a b", "c d")])
        local = self.app / "declan" / "core" / ".data" / "conversations.sqlite3"
        make_database(local, phrases=[("e f", "g h")])
        broken = self.root / "releases" / "old" / "declan" / "core" / ".data" / "conversations.sqlite3"
        broken.parent.mkdir(parents=True)
        broken.write_bytes(b"not a database")
        logger = Mock()
        reports = data_location_repair.repair(self.app, self.target, logger=logger)
        self.assertEqual([r["source"] for r in reports], [str(local)])
        self.assertEqual(dict(rows(self.target, "SELECT phrase, target FROM learned_intents")),
                         {"a b": "c d", "e f": "g h"})
        logger.error.assert_called_once()
        self.assertTrue(broken.exists())

    def test_previous_and_releases_entries_for_the_same_folder_merge_once(self):
        make_database(self.target)
        make_database(self.stray, turns=["once"])
        data_location_repair.repair(self.app, self.target)
        self.assertEqual(rows(self.target, "SELECT count(*) FROM turns WHERE message = 'once'"), [(1,)])

    def test_history_hook_skips_redirected_databases(self):
        with patch.object(history, "DATABASE", self.target), \
                patch.object(data_location_repair, "repair") as repair:
            self.assertEqual(history.repair_data_location(), [])
        repair.assert_not_called()


class StartupTests(unittest.TestCase):
    def test_lifecycle_runs_the_repair_before_initialising(self):
        source = (ROOT / "server_lifecycle.py").read_text()
        self.assertLess(source.index("repair(logger)"), source.index("history_store.initialize()"))


if __name__ == "__main__":
    os.environ.setdefault("DECLAN_HISTORY_RETENTION_DAYS", "30")
    unittest.main()
