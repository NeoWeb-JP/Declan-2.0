"""Prevent mutable GitHub-owned action tags from returning to CI workflows."""

from pathlib import Path
import re
import unittest


WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
ACTION_USE = re.compile(r"^\s*-?\s*uses:\s*actions/([^@\s]+)@([^\s#]+)", re.MULTILINE)
PINNED_SHA = re.compile(r"[0-9a-f]{40}\Z")


class GithubActionPinTests(unittest.TestCase):
    def test_github_owned_actions_use_immutable_commit_shas(self):
        workflows = sorted((*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")))
        self.assertTrue(workflows, "No GitHub Actions workflows found")
        unpinned = []
        for workflow in workflows:
            for match in ACTION_USE.finditer(workflow.read_text(encoding="utf-8")):
                if not PINNED_SHA.fullmatch(match.group(2)):
                    unpinned.append(f"{workflow.name}: actions/{match.group(1)}@{match.group(2)}")
        self.assertEqual(unpinned, [], "Pin GitHub-owned actions to full commit SHAs")


if __name__ == "__main__":
    unittest.main()
