import unittest
from unittest.mock import MagicMock, patch

from src.speaker_beep import (
    SpeakerBeep,
    SpeakerBeepError,
    _pick_output_device,
    _tone_pcm,
)


class SpeakerBeepTests(unittest.TestCase):
    def test_tone_pcm_stereo_size(self):
        pcm = _tone_pcm(880.0, 0.1, 16_000, channels=2, gain=0.3)
        self.assertEqual(len(pcm), 1600 * 2 * 2)

    def test_pick_prefers_headphones(self):
        fake_sd = MagicMock()
        fake_sd.query_devices.return_value = [
            {
                "name": "snd_rpi_googlevoicehat_soundcar: VoiceHAT",
                "max_output_channels": 2,
            },
            {
                "name": "bcm2835 Headphones: - (hw:3,0)",
                "max_output_channels": 8,
            },
        ]
        self.assertEqual(_pick_output_device(fake_sd, None), 1)

    def test_pick_honors_explicit_device(self):
        fake_sd = MagicMock()
        self.assertEqual(_pick_output_device(fake_sd, 0), 0)

    def test_beep_writes_to_output_stream(self):
        fake_sd = MagicMock()
        fake_sd.query_devices.return_value = {
            "name": "bcm2835 Headphones",
            "default_samplerate": 48000.0,
            "max_output_channels": 8,
        }
        stream = MagicMock()
        fake_sd.RawOutputStream.return_value.__enter__.return_value = stream

        beep = SpeakerBeep.__new__(SpeakerBeep)
        beep._sounddevice = fake_sd
        beep.device = 1
        beep.frequency_hz = 880.0
        beep.duration = 0.05
        beep.gain = 0.3
        beep.device_name = "bcm2835 Headphones"
        beep.sample_rate = 48000
        beep.channels = 2
        beep.beep(count=1)

        kwargs = fake_sd.RawOutputStream.call_args.kwargs
        self.assertEqual(kwargs["device"], 1)
        stream.write.assert_called_once()

    def test_missing_sounddevice_raises(self):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "sounddevice":
                raise ImportError("no sd")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(SpeakerBeepError):
                SpeakerBeep()


if __name__ == "__main__":
    unittest.main()
