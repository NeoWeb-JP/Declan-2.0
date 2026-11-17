"""Keep proprietary HACS validation blocking with only its licence exception."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class HacsWorkflowTests(unittest.TestCase):
    def test_hacs_check_has_only_the_proprietary_license_exception(self):
        workflow = (ROOT / ".github/workflows/hacs-validation.yml").read_text(encoding="utf-8")
        self.assertRegex(workflow, r"uses: hacs/action@[0-9a-f]{40}\b")
        self.assertEqual(re.findall(r"^\s+ignore:\s*(.+)$", workflow, re.MULTILINE), ["license"])
        self.assertIn("category: integration", workflow)
        self.assertIn("comment: false", workflow)
        self.assertNotIn("continue-on-error", workflow)
        self.assertNotIn("pull_request_target", workflow)
        self.assertNotIn("paths:", workflow)
        self.assertNotIn("paths-ignore:", workflow)
        self.assertIn("  pull_request:\n    branches: [main]", workflow)
        self.assertIn("  push:\n    branches: [main]", workflow)
        self.assertIn("  workflow_dispatch:", workflow)
        self.assertIn("  contents: read", workflow)
        self.assertNotIn(": write", workflow)

    def test_local_brand_icon_is_present_for_the_enabled_brand_check(self):
        icon = (ROOT / "custom_components/declan_two/brand/icon.png").read_bytes()
        self.assertTrue(icon.startswith(b"\x89PNG\r\n\x1a\n"))
