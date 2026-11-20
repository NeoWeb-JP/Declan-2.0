"""HIS-11: per-speaker match rate from reviewed VoicePipeline attributions."""
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from declan.voice import voicepipeline as vp

ROOT = Path(__file__).resolve().parents[1]


def row(matched, assigned, status="confirmed"):
    return {"matched_speaker": matched, "current_assigned_to": assigned, "status": status}


class MatchRateTests(unittest.TestCase):
    def test_kept_over_reviewed_with_minimum_of_five(self):
        rows = ([row("Jaco", "Jaco")] * 4 + [row("Jaco", "Ed", "corrected")]
                + [row("Ed", "Ed")] * 3
                + [row("Jaco", "", "pending"), row("Jaco", "Jaco", "dismissed"), row("Jaco", "Jaco", "rejected"),
                   row("Jaco", "Jaco", "discarded"), row("", "Ed"), row("Ed", None), None, "x"])
        result = vp.match_rates(rows)
        self.assertEqual(result["speakers"]["Jaco"], {"reviewed": 5, "kept": 4, "rate": 0.8})
        self.assertEqual(result["speakers"]["Ed"], {"reviewed": 3, "kept": 3, "rate": None})
        self.assertEqual(result["overall"], {"reviewed": 8, "kept": 7, "rate": 0.875})
        self.assertEqual(result["minimum_reviews"], 5)

    def test_name_comparison_ignores_case_and_spacing(self):
        result = vp.match_rates([row("Ed ", "ed")] * 5)
        self.assertEqual(result["speakers"]["Ed"]["rate"], 1.0)

    def test_listing_survives_history_failure(self):
        def fake(method, path, body=None, **kwargs):
            if path.endswith("/history"):
                raise vp.PipelineError("down")
            return []
        with patch.object(vp, "request", side_effect=fake):
            self.assertIsNone(vp.listing()["match_rates"])


class ProxyAndPanelTests(unittest.TestCase):
    def setUp(self):
        web = SimpleNamespace(json_response=lambda *a, **k: None)
        aiohttp = SimpleNamespace(web=web, ClientTimeout=lambda total: total, ClientError=OSError)
        self.enterContext(patch.dict("sys.modules", {
            "aiohttp": aiohttp, "homeassistant": SimpleNamespace(), "homeassistant.components": SimpleNamespace(),
            "homeassistant.components.http": SimpleNamespace(HomeAssistantView=object),
            "homeassistant.helpers": SimpleNamespace(),
            "homeassistant.helpers.aiohttp_client": SimpleNamespace(async_get_clientsession=lambda hass: None),
        }))
        spec = importlib.util.spec_from_file_location(
            "voice_review_view_fixture", ROOT / "custom_components/declan_two/voice_review_view.py")
        assert spec is not None and spec.loader is not None
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_proxy_keeps_only_valid_counts(self):
        safe = self.module.safe_match_rates({
            "speakers": {"Jaco": {"reviewed": 5, "kept": 4, "rate": 0.8},
                         "Ed": {"reviewed": 2, "kept": 3, "rate": None},
                         "": {"reviewed": 1, "kept": 1, "rate": None}},
            "overall": {"reviewed": 5, "kept": 4, "rate": 0.8}, "minimum_reviews": 5, "extra": "x"})
        self.assertEqual(safe, {"speakers": {"Jaco": {"reviewed": 5, "kept": 4, "rate": 0.8}},
                                "overall": {"reviewed": 5, "kept": 4, "rate": 0.8}, "minimum_reviews": 5})
        self.assertIsNone(self.module.safe_match_rates(None))

    def test_panel_shows_match_rate(self):
        js = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
        self.assertIn("matchRateText(rates, entry)", js)
        self.assertIn("'Match rate: n/a ('", js)
        self.assertIn('"match_rates": safe_match_rates(data.get("match_rates"))',
                      (ROOT / "custom_components/declan_two/voice_review_view.py").read_text())


if __name__ == "__main__":
    unittest.main()
