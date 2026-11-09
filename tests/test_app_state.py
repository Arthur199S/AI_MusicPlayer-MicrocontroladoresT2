import unittest

from src.app_state import AppState


class AppStateTests(unittest.TestCase):
    def test_record_stt_increments_counters(self):
        state = AppState()
        state.record_stt(
            "toque evidencias",
            input_tokens=10,
            output_tokens=3,
            total_tokens=13,
            audio_seconds=1.5,
        )
        snap = state.snapshot()
        self.assertEqual(snap["request_count"], 1)
        self.assertEqual(snap["stt_calls"], 1)
        self.assertEqual(snap["transcribed_lines"], 1)
        self.assertEqual(snap["transcribed_chars"], len("toque evidencias"))
        self.assertEqual(snap["input_tokens"], 10)
        self.assertEqual(snap["output_tokens"], 3)
        self.assertEqual(snap["total_tokens"], 13)
        self.assertEqual(snap["recognized_phrase"], "toque evidencias")
        self.assertEqual(snap["audio_seconds_est"], 1.5)

    def test_playing_updates_last_track(self):
        state = AppState()
        state.set_playing("musica a")
        state.set_playing("musica b")
        snap = state.snapshot()
        self.assertEqual(snap["current_track"], "musica b")
        self.assertEqual(snap["last_track"], "musica a")
        self.assertEqual(snap["app_status"], "playing")
        self.assertEqual(snap["app_status_code"], 4)
        self.assertEqual(snap["tracks_today"], 2)
        self.assertEqual(snap["recent_tracks"], ["musica b", "musica a"])

    def test_recent_tracks_keeps_last_five(self):
        state = AppState()
        for name in ("a", "b", "c", "d", "e", "f"):
            state.set_playing(name)
        self.assertEqual(state.snapshot()["recent_tracks"], ["f", "e", "d", "c", "b"])

    def test_record_stt_stores_latency(self):
        state = AppState()
        state.record_stt("oi", latency_ms=321.4)
        snap = state.snapshot()
        self.assertEqual(snap["last_stt_latency_ms"], 321.4)


if __name__ == "__main__":
    unittest.main()
