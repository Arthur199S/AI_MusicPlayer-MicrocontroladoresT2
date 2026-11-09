import unittest
from unittest.mock import MagicMock

from src.app_state import AppState, status_code
from src.player import seconds_left_from
from src.ubidots_mqtt import UbidotsMqttBridge, _parse_lv


class StatusCodeTests(unittest.TestCase):
    def test_known_statuses(self):
        self.assertEqual(status_code("stopped"), 0)
        self.assertEqual(status_code("listening_wake"), 1)
        self.assertEqual(status_code("recording"), 2)
        self.assertEqual(status_code("transcribing"), 3)
        self.assertEqual(status_code("playing"), 4)
        self.assertEqual(status_code("paused"), 5)
        self.assertEqual(status_code("error"), 6)

    def test_unknown_defaults_to_zero(self):
        self.assertEqual(status_code("whatever"), 0)


class TracksTodayTests(unittest.TestCase):
    def test_set_playing_increments_tracks_today(self):
        state = AppState()
        state.set_playing("a")
        state.set_playing("b")
        self.assertEqual(state.snapshot()["tracks_today"], 2)

    def test_day_roll_resets_tracks_today(self):
        state = AppState()
        state.set_playing("a")
        self.assertEqual(state.tracks_today, 1)
        state.day_key = "2000-01-01"
        state.set_playing("b")
        snap = state.snapshot()
        self.assertEqual(snap["tracks_today"], 1)
        self.assertNotEqual(snap["day_key"], "2000-01-01")


class SecondsLeftTests(unittest.TestCase):
    def test_seconds_left(self):
        self.assertEqual(seconds_left_from(100.0, 40.0), 60.0)
        self.assertEqual(seconds_left_from(10.0, 12.0), 0.0)
        self.assertIsNone(seconds_left_from(None, 1.0))
        self.assertIsNone(seconds_left_from(10.0, None))


class DownlinkTests(unittest.TestCase):
    def test_parse_lv(self):
        self.assertEqual(_parse_lv(b"1"), 1.0)
        self.assertEqual(_parse_lv("0"), 0.0)
        self.assertIsNone(_parse_lv(b"abc"))

    def _bridge(self, state, *, paused=None):
        player = MagicMock()
        player.playback_snapshot.return_value = {
            "alive": paused is not None,
            "paused": paused,
            "time_pos": None,
            "duration": None,
            "seconds_left": None,
        }
        bridge = UbidotsMqttBridge(state, player)
        bridge._client = MagicMock()
        return bridge, player

    def test_pause_echo_does_not_toggle_back(self):
        state = AppState()
        state.set_playing("evidencias")
        state.clear_current_track(paused=True)
        bridge, player = self._bridge(state, paused=True)
        # Eco de cmd_pause=1 estando pausado: nao pode despausar nem republicar.
        bridge.handle_command("cmd_pause", 1)
        player.set_pause.assert_not_called()
        player.resume.assert_not_called()

    def test_zero_echo_while_playing_is_noop(self):
        state = AppState()
        state.set_playing("evidencias")
        bridge, player = self._bridge(state, paused=False)
        bridge.handle_command("cmd_pause", 0)
        player.set_pause.assert_not_called()
        self.assertEqual(state.app_status, "playing")

    def test_periodic_payload_has_no_cmd_vars(self):
        state = AppState()
        bridge, _ = self._bridge(state)
        payload = bridge.build_payload()
        self.assertNotIn("cmd_pause", payload)
        self.assertNotIn("cmd_resume", payload)

    def test_publish_events_only_sends_changes(self):
        import json

        state = AppState()
        bridge, _ = self._bridge(state)
        bridge._running = True
        bridge.publish_now()  # baseline completo
        bridge._client.publish.reset_mock()

        # Nada mudou -> zero dots.
        self.assertEqual(bridge.publish_events(), {})
        bridge._client.publish.assert_not_called()

        # Comecou musica -> so variaveis de evento (+ seconds_left), sem cpu/temp/ram.
        state.set_playing("Old Stories")
        sent = bridge.publish_events()
        self.assertIn("now_playing", sent)
        self.assertIn("app_status", sent)
        self.assertIn("tracks_today", sent)
        self.assertNotIn("cpu_percent", sent)
        self.assertNotIn("temp_c", sent)
        self.assertNotIn("heartbeat", sent)
        body = json.loads(bridge._client.publish.call_args.args[1])
        self.assertEqual(body["now_playing"]["context"]["track"], "Old Stories")

        # Repetir sem mudanca -> nada.
        bridge._client.publish.reset_mock()
        self.assertEqual(bridge.publish_events(), {})

    def test_default_interval_is_budget_friendly(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("UBIDOTS_PUBLISH_INTERVAL", None)
            bridge = UbidotsMqttBridge(AppState(), MagicMock())
        self.assertGreaterEqual(bridge.publish_interval, 300)

    def test_voice_pause_syncs_switch_once(self):
        state = AppState()
        state.set_playing("evidencias")
        state.clear_current_track(paused=True)
        bridge, _ = self._bridge(state)
        bridge._sync_cmd_switches()
        bridge._sync_cmd_switches()
        self.assertEqual(bridge._client.publish.call_count, 1)

    def test_cmd_pause_calls_player(self):
        state = AppState()
        state.set_playing("evidencias")
        bridge, player = self._bridge(state, paused=False)
        bridge.handle_command("cmd_pause", 1)
        player.set_pause.assert_called_once_with(True)
        self.assertEqual(state.app_status, "paused")
        # Switch permanece em 1 enquanto pausado.
        sent = [
            (c.args[1] if c.args else c[0][1]).replace(" ", "")
            for c in bridge._client.publish.call_args_list
        ]
        self.assertTrue(any('"cmd_pause":1' in s for s in sent))

    def test_cmd_resume_calls_player(self):
        state = AppState()
        state.set_playing("x")
        state.clear_current_track(paused=True)
        bridge, player = self._bridge(state, paused=True)
        bridge.handle_command("cmd_resume", 1)
        player.set_pause.assert_called_once_with(False)
        self.assertEqual(state.app_status, "playing")
        published = bridge._client.publish.call_args_list[0]
        payload = published.args[1] if published.args else published[0][1]
        self.assertIn('"cmd_pause":0', payload.replace(" ", ""))

    def test_cmd_pause_zero_resumes(self):
        state = AppState()
        state.set_playing("x")
        state.clear_current_track(paused=True)
        bridge, player = self._bridge(state, paused=True)
        bridge.handle_command("cmd_pause", 0)
        player.set_pause.assert_called_once_with(False)
        self.assertEqual(state.app_status, "playing")

    def test_build_payload_shape(self):
        state = AppState()
        state.set_playing("evidencias")
        state.set_e2e_latency_ms(1234.5)
        state.record_stt("x", latency_ms=200.0)
        player = MagicMock()
        player.playback_snapshot.return_value = {
            "alive": True,
            "paused": False,
            "time_pos": 10.0,
            "duration": 100.0,
            "seconds_left": 90.0,
        }
        bridge = UbidotsMqttBridge(state, player)
        payload = bridge.build_payload()
        self.assertEqual(payload["app_status"], 4)
        self.assertEqual(payload["now_playing"]["value"], 1)
        self.assertEqual(payload["now_playing"]["context"]["track"], "evidencias")
        self.assertEqual(payload["now_playing"]["context"]["text"], "evidencias")
        self.assertEqual(payload["tracks_today"], 1)
        self.assertEqual(payload["seconds_left"], 90.0)
        self.assertEqual(payload["heartbeat"], 1)
        self.assertEqual(payload["stt_latency_ms"], 200.0)
        self.assertEqual(payload["e2e_latency_ms"], 1234.5)

    def test_now_playing_empty_is_nada_tocando(self):
        state = AppState()
        player = MagicMock()
        player.playback_snapshot.return_value = {
            "alive": False,
            "paused": None,
            "time_pos": None,
            "duration": None,
            "seconds_left": None,
        }
        bridge = UbidotsMqttBridge(state, player)
        payload = bridge.build_payload()
        self.assertEqual(payload["now_playing"]["value"], 0)
        self.assertEqual(payload["now_playing"]["context"]["track"], "nada tocando")

    def test_now_playing_keeps_track_while_listening_wake(self):
        state = AppState()
        state.set_playing("evidencias")
        state.set_listening_wake()  # nao deve apagar "playing"
        self.assertEqual(state.app_status, "playing")
        player = MagicMock()
        player.playback_snapshot.return_value = {
            "alive": True,
            "paused": False,
            "time_pos": 5.0,
            "duration": 200.0,
            "seconds_left": 195.0,
        }
        bridge = UbidotsMqttBridge(state, player)
        payload = bridge.build_payload()
        self.assertEqual(payload["now_playing"]["value"], 1)
        self.assertEqual(payload["now_playing"]["context"]["track"], "evidencias")


if __name__ == "__main__":
    unittest.main()
