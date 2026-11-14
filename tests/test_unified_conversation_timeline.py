"""Unified activity timeline keeps speaker actions attached to recordings."""
from pathlib import Path
import unittest

JS = (Path(__file__).resolve().parents[1] / "custom_components/declan_two/frontend/panel.js").read_text()

class UnifiedTimelineTests(unittest.TestCase):
    def test_single_primary_activity_view(self):
        self.assertIn('data-tab="conversations">Conversations &amp; Voice', JS)
        self.assertNotIn('data-tab="voices"', JS)
        self.assertIn('class="timeline-list"', JS)
        self.assertIn('class="timeline-filter"', JS)

    def test_review_in_row(self):
        for snippet in ("async loadTimeline()", "renderTimeline()", "this.resolveVoice(item.id",
                        "this.correctVoiceHistory(item, select.value)", "this.playVoice(item.id, play,",
                        "this.resolveVoice(item.id, 'dismiss', null)", "this.resolveVoice(item.id, 'enrol', trimmed)"):
            self.assertIn(snippet, JS)

    def test_no_unsafe_transcript_join(self):
        self.assertIn("no verified shared interaction ID", JS)
        self.assertIn("kind:'conversation'", JS)
        self.assertIn("Speaker not linked", JS)
        self.assertIn("textContent = item.transcript || item.message", JS)
        self.assertNotIn("transcript.innerHTML", JS)

    def test_confirmed_recordings_stay_visible_and_playable(self):
        self.assertIn("recordings.set(item.id, {kind:'pending', item})", JS)
        self.assertIn("recordings.set(item.id, {kind:'reviewed', item})", JS)
        self.assertIn("Date.parse(a.item.recorded_at || '')", JS)
        self.assertIn("save.textContent = reviewed ? (editing ? 'Save change' : 'Change speaker') : 'Confirm';", JS)
        self.assertIn("play.textContent = 'Play'", JS)
        self.assertIn("this.playVoice(item.id, play,", JS)

    def test_clear_review_state(self):
        self.assertIn("state.textContent = reviewState === 'pending' ? 'Needs review'", JS)
        self.assertIn("'Rejected' : 'Confirmed'", JS)
        self.assertIn("card.classList.add('timeline-row--' + reviewState)", JS)
        self.assertIn("timeline-status-label--pending", JS)
        self.assertIn("timeline-status-label--confirmed", JS)
        self.assertIn("timeline-status-label--rejected", JS)
        self.assertIn('value="reviewed">Reviewed', JS)

    def test_reviewed_speaker_is_locked_until_change_clicked(self):
        self.assertIn("select.disabled = reviewed;", JS)
        self.assertIn("if (reviewed && !editing)", JS)
        self.assertIn("select.disabled = false;", JS)
        self.assertIn("select.disabled = true;", JS)
        self.assertIn("save.textContent = reviewed ? (editing ? 'Save change' : 'Change speaker') : 'Confirm';", JS)
        self.assertIn("cancel.textContent = 'Cancel';", JS)

    def test_filters_and_collapsed_details(self):
        for snippet in ('value="all"', 'value="pending"', 'value="reviewed"',
                        "document.createElement('details')", "summary.textContent = 'More details'"):
            self.assertIn(snippet, JS)

if __name__ == "__main__":
    unittest.main()
