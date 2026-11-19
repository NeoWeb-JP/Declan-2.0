"""Source-location preflight detects moved expressions in legacy tests."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_refactor_test_anchors as anchors


class RefactorAnchorTests(unittest.TestCase):
    def test_recognizes_root_read_text_and_joinpath(self):
        tree = anchors.ast.parse(
            'SERVER = (ROOT / "server.py").read_text()\n'
            'source = Path(__file__).resolve().parents[1].joinpath("server.py").read_text()\n'
        )
        self.assertEqual(anchors.referenced_source_files(tree),
                         {"SERVER": "server.py", "source": "server.py"})

    def test_reports_removed_assertion_and_index_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "server.py").write_text("new_call()\n")
            (root / "tests" / "test_contract.py").write_text(
                'from pathlib import Path\n'
                'ROOT = Path(__file__).resolve().parents[1]\n'
                'SERVER = (ROOT / "server.py").read_text()\n'
                'def test_contract():\n'
                '    assert "old_call()" in SERVER\n'
                '    SERVER.index("old_call()")\n'
            )
            with patch.object(anchors, "changed_python_files", return_value=["server.py"]), \
                 patch.object(anchors, "source_at_ref", return_value="old_call()\n"):
                findings = anchors.check("origin/main", root)
        self.assertEqual(len(findings), 1)
        self.assertIn("old_call()", findings[0])

    def test_detects_plain_assertions_and_source_methods(self):
        tree = anchors.ast.parse(
            'assert "old_call()" in SERVER\n'
            'SERVER.index("old_call()")\n'
            'SERVER.find("old_call()")\n'
            'SERVER.count("old_call()")\n'
            'SERVER.startswith("old_call()")\n'
            'self.assertIn("old_call()", SERVER)\n'
        )
        references = list(anchors.anchor_references(tree))
        self.assertEqual(len(references), 6)
        self.assertTrue(all(variable == "SERVER" and literal == "old_call()"
                            for _, variable, literal in references))

    def test_ignores_unrelated_comparisons(self):
        tree = anchors.ast.parse(
            'assert value in mapping\n'
            'assert "hello" not in SERVER\n'
            'assert SERVER.find(variable) >= 0\n'
        )
        self.assertEqual(list(anchors.anchor_references(tree)), [])

    def test_unchanged_anchor_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "server.py").write_text("old_call()\nnew_call()\n")
            (root / "tests" / "test_contract.py").write_text(
                'from pathlib import Path\n'
                'ROOT = Path(__file__).resolve().parents[1]\n'
                'SERVER = (ROOT / "server.py").read_text()\n'
                'class Contract:\n'
                '    def check(self):\n'
                '        self.assertIn("old_call()", SERVER)\n'
            )
            with patch.object(anchors, "changed_python_files", return_value=["server.py"]), \
                 patch.object(anchors, "source_at_ref", return_value="old_call()\n"):
                self.assertEqual(anchors.check("origin/main", root), [])


if __name__ == "__main__":
    unittest.main()
