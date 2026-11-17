"""Check local Markdown links in the primary operator documentation."""
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    "README.md",
    "docs/installation.md",
    "docs/environment.md",
    "docs/architecture.md",
    "docs/now-work.md",
    "docs/p1-security.md",
)
LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")


class DocumentationLinksTests(unittest.TestCase):
    def test_internal_documentation_links_resolve(self):
        checked = 0
        for name in DOCUMENTS:
            document = ROOT / name
            content = document.read_text(encoding="utf-8")
            for raw in LINK.findall(content):
                url = urlsplit(raw.strip())
                if url.scheme or url.netloc or raw.startswith("#"):
                    continue
                destination = (document.parent / unquote(url.path)).resolve()
                with self.subTest(document=name, link=raw):
                    self.assertTrue(destination.is_relative_to(ROOT.resolve()))
                    self.assertTrue(destination.is_file(), f"Missing documentation target: {raw}")
                checked += 1
        self.assertGreater(checked, 0, "No internal documentation links were checked")


if __name__ == "__main__":
    unittest.main()
