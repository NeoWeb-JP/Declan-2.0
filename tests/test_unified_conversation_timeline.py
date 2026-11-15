"""Contract tests for one seven-day voice-recording review workspace."""
from pathlib import Path
import unittest

JS = (Path(__file__).resolve().parents[1] / "custom_components/declan_two/frontend/panel.js").read_text()
TIMELINE = JS.split("  async loadTimeline() {", 1)[1].split("  async loadLearnedIntents() {", 1)[0]
HISTORY = JS.split('id="panel-conversations"', 1)[1].split('id="panel-players"', 1)[0]


class UnifiedTimelineTests(unittest.TestCase):
    def test_initial_mount_activates_selected_tab(self):
        self.assertIn("this.selectTab('overview');", JS)
        self.assertIn("panel.hidden = panel.id !== 'panel-' + name;", JS)
        self.assertIn("this.closePageMenu();", JS)

    def test_one_history_page_with_three_voice_review_categories(self):
        for label in ("Unconfirmed", "Confirmed", "Rejected"):
            self.assertIn("sectionFor('" + label + "'", TIMELINE)
        self.assertNotIn("Conversation history", TIMELINE)
        self.assertNotIn("Saved phrase corrections", HISTORY)
        self.assertNotIn('class="timeline-filter"', HISTORY)
        self.assertIn("declan_two/history?recording_ids=", TIMELINE)
        self.assertIn('class="timeline-list"', HISTORY)

    def test_no_duplicate_recordings_or_conversation_only_rows(self):
        self.assertIn("const recordings = new Map();", TIMELINE)
        self.assertIn("recordings.set(String(item.id), {kind:'pending', item})", TIMELINE)
        self.assertIn("!recordings.has(String(item.id))", TIMELINE)
        self.assertNotIn("kind:'conversation'", TIMELINE)
        self.assertIn("Never merge recordings and conversation turns by text or time", TIMELINE)

    def test_seven_day_cutoff_for_all_statuses(self):
        self.assertIn("Date.now() - 7 * 24 * 60 * 60 * 1000", TIMELINE)
        self.assertIn("Number.isFinite(recorded)", TIMELINE)
        self.assertIn("recent(item)", TIMELINE)
        self.assertIn("No recordings from the last 7 days.", TIMELINE)

    def test_per_phrase_collapsed_sections(self):
        for section in ("Voice matching", "Teach Declan", "Declan's response", "Diagnostics"):
            self.assertIn(section, TIMELINE)
        self.assertIn("entry.open = pending;", TIMELINE)
        self.assertIn("subsection(card, 'Voice matching', pending)", TIMELINE)
        self.assertIn("train.disabled = !verified;", TIMELINE)
        self.assertIn("verified conversation link", TIMELINE)
        self.assertIn("item.reply || 'Not available'", TIMELINE)
        self.assertIn("Recording ID:", TIMELINE)

    def test_confirm_reject_play_and_speaker_correction(self):
        self.assertIn("this.resolveVoice(item.id, select.value === suggested ? 'confirm' : 'assign', select.value)", TIMELINE)
        self.assertIn("this.correctVoiceHistory(item, select.value)", TIMELINE)
        self.assertIn("this.resolveVoice(item.id, 'dismiss', null)", TIMELINE)
        self.assertNotIn("Enrol new speaker", TIMELINE)
        self.assertIn("this.playVoice(item.id, play,", TIMELINE)
        self.assertIn("select.disabled = reviewed;", TIMELINE)
        self.assertIn("if (reviewed && !editing)", TIMELINE)
        self.assertIn("cancel.textContent = 'Cancel';", TIMELINE)

    def test_settings_does_not_duplicate_review(self):
        settings = JS.split('id="panel-settings"', 1)[1].split('id="panel-updates"', 1)[0]
        self.assertNotIn("Reviewed recordings</h3>", settings)
        self.assertNotIn("Refresh learned commands", settings)
        self.assertNotIn("Conversation archive</h3>", settings)
        self.assertIn('class="page-navigation" aria-label="Declan pages" hidden', JS)


if __name__ == "__main__":
    unittest.main()
