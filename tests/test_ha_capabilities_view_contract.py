"""Static security contract checks; run without Home Assistant installed."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "declan_two"


class CapabilitiesViewContractTests(unittest.TestCase):
    def test_view_requires_home_assistant_authentication(self):
        source = (ROOT / "capabilities_view.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        view = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                    and node.name == "DeclanCapabilitiesView")
        assignments = {
            target.id: node.value for node in view.body
            if isinstance(node, ast.Assign) for target in node.targets
            if isinstance(target, ast.Name)
        }
        self.assertEqual(ast.literal_eval(assignments["url"]), "/api/declan_two/capabilities")
        self.assertIs(ast.literal_eval(assignments["requires_auth"]), True)
        self.assertIn('allow_redirects=False', source)
        self.assertIn('"Cache-Control": "no-store"', source)
        self.assertIn('check_server_compatibility(payload)', source)
        self.assertNotIn('"token":', source)
        self.assertIn('headers={"Authorization": f"Bearer {entry.data[\\'token\']}"}', source)

    def test_route_registered_once_at_integration_setup(self):
        source = (ROOT / "__init__.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        setup = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                     and node.name == "async_setup")
        self.assertIn("register_view(DeclanCapabilitiesView())", ast.get_source_segment(source, setup))
        entry_setup = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                           and node.name == "async_setup_entry")
        self.assertNotIn("register_view", ast.get_source_segment(source, entry_setup))


if __name__ == "__main__":
    unittest.main()
