"""Prevent mutable third-party GitHub Action refs from returning to CI."""

from pathlib import Path
import re
import unittest


WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
ACTION_USE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
PINNED_SHA = re.compile(r"[0-9a-f]{40}\Z")


class GithubActionPinTests(unittest.TestCase):
    def test_remote_actions_use_immutable_commit_shas(self):
        workflows = sorted((*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")))
        self.assertTrue(workflows, "No GitHub Actions workflows found")
        unpinned = []
        for workflow in workflows:
            for match in ACTION_USE.finditer(workflow.read_text(encoding="utf-8")):
                action = match.group(1)
                if action.startswith("./") or action.startswith("docker://"):
                    continue
                if "@" not in action or not PINNED_SHA.fullmatch(action.rsplit("@", 1)[1]):
                    unpinned.append(f"{workflow.name}: {action}")
        self.assertEqual(unpinned, [], "Pin remote actions to full commit SHAs")


if __name__ == "__main__":
    unittest.main()
