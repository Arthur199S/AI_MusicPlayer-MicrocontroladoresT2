import unittest
from unittest.mock import MagicMock, patch

from src.buzzer import DEFAULT_BUZZER_GPIO, DEFAULT_BUZZER_MODE, Buzzer, BuzzerError


class BuzzerTests(unittest.TestCase):
    def test_default_pin_is_voicehat_driver2(self):
        self.assertEqual(DEFAULT_BUZZER_GPIO, 27)
        self.assertEqual(DEFAULT_BUZZER_MODE, "tone")

    def test_missing_lgpio_raises(self):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "lgpio":
                raise ImportError("no lgpio")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with patch("src.buzzer._SYSTEM_DIST_PACKAGES", "/tmp/does-not-exist"):
                with self.assertRaises(BuzzerError):
                    Buzzer(pin=27)

    def test_open_failure_raises(self):
        fake_lgpio = MagicMock()
        fake_lgpio.gpiochip_open.side_effect = OSError("busy")

        with patch("src.buzzer._import_lgpio", return_value=fake_lgpio):
            with self.assertRaises(BuzzerError) as ctx:
                Buzzer(pin=27)
        self.assertIn("GPIO 27", str(ctx.exception))

    def test_tone_beep_uses_pwm(self):
        fake_lgpio = MagicMock()
        fake_lgpio.gpiochip_open.return_value = 42

        with patch("src.buzzer._import_lgpio", return_value=fake_lgpio):
            buzzer = Buzzer(pin=27, mode="tone", frequency_hz=2000)
            buzzer.beep(duration=0.0, count=1, gap=0.0)
            buzzer.close()

        fake_lgpio.gpio_claim_output.assert_called_once_with(42, 27)
        pwm_calls = fake_lgpio.tx_pwm.call_args_list
        # on: 2000 Hz 50%, off: 0,0 (beep off + close off)
        self.assertTrue(
            any(call.args[:3] == (42, 27, 2000) for call in pwm_calls)
        )
        self.assertTrue(
            any(call.args[:4] == (42, 27, 0, 0) for call in pwm_calls)
        )

    def test_active_beep_toggles_gpio(self):
        fake_lgpio = MagicMock()
        fake_lgpio.gpiochip_open.return_value = 42

        with patch("src.buzzer._import_lgpio", return_value=fake_lgpio):
            buzzer = Buzzer(pin=27, mode="active")
            buzzer.beep(duration=0.0, count=2, gap=0.0)
            buzzer.close()

        writes = [call.args for call in fake_lgpio.gpio_write.call_args_list]
        self.assertIn((42, 27, 1), writes)
        self.assertIn((42, 27, 0), writes)

    def test_active_low_inverts_levels(self):
        fake_lgpio = MagicMock()
        fake_lgpio.gpiochip_open.return_value = 7

        with patch("src.buzzer._import_lgpio", return_value=fake_lgpio):
            buzzer = Buzzer(pin=22, active_high=False, mode="active")
            buzzer.on()
            buzzer.off()
            buzzer.close()

        levels = [call.args[2] for call in fake_lgpio.gpio_write.call_args_list]
        self.assertEqual(levels[0], 1)
        self.assertIn(0, levels)


if __name__ == "__main__":
    unittest.main()
