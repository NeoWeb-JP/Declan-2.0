"""Spotify credential editor follows native panel form styling."""
from pathlib import Path
import unittest

JS = (Path(__file__).resolve().parents[1] / "custom_components/declan_two/frontend/panel.js").read_text()

class SpotifySettingsStyleTests(unittest.TestCase):
    def test_form_matches_native_theme(self):
        for fragment in (".spotify-form input {", "background:#102635", "border:1px solid #315568",
                         "border-radius:9px", ".spotify-form label {", ".spotify-form input:focus-visible",
                         "@media(max-width:520px)", ".spotify-form button { width:100%; }"):
            self.assertIn(fragment, JS)
    def test_existing_secret_not_prefilled(self):
        self.assertIn('autocomplete="new-password"', JS)
        self.assertIn("window.confirm(", JS)
        self.assertIn("form.reset()", JS)

if __name__ == "__main__":
    unittest.main()
