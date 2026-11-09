import unittest
from unittest.mock import MagicMock, patch

from src.command_parser import contains_wake_word
from src.openai_transcribe import TranscriptionError, TranscriptionResult, transcribe_audio


class ContainsWakeWordTests(unittest.TestCase):
    def test_detects_variants(self):
        self.assertTrue(contains_wake_word("Jarvis"))
        self.assertTrue(contains_wake_word("assistente toque algo"))
        self.assertTrue(contains_wake_word("oi jarbas"))
        self.assertFalse(contains_wake_word("toque evidencias"))


class OpenAITranscribeTests(unittest.TestCase):
    def test_requires_api_key(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            with self.assertRaises(TranscriptionError) as ctx:
                transcribe_audio(b"fake-wav", api_key="")
            self.assertIn("OPENAI_API_KEY", str(ctx.exception))

    def test_transcribes_with_mocked_client(self):
        fake_result = MagicMock()
        fake_result.text = "  toque evidencias  "
        fake_result.usage = MagicMock(
            input_tokens=120, output_tokens=8, total_tokens=128
        )

        fake_client = MagicMock()
        fake_client.audio.transcriptions.create.return_value = fake_result

        env = {
            "OPENAI_API_KEY": "",
            "OPENAI_STT_LANGUAGE": "pt",
            "OPENAI_STT_LANGUAGES": "",
            "OPENAI_STT_PROMPT": "",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch("openai.OpenAI", return_value=fake_client) as openai_cls:
                result = transcribe_audio(
                    b"RIFF-fake",
                    api_key="sk-test",
                    model="gpt-4o-mini-transcribe",
                    prompt="pt-en music commands",
                )

        self.assertIsInstance(result, TranscriptionResult)
        self.assertEqual(result.text, "toque evidencias")
        self.assertEqual(result.input_tokens, 120)
        self.assertEqual(result.output_tokens, 8)
        self.assertEqual(result.total_tokens, 128)
        openai_cls.assert_called_once_with(api_key="sk-test")
        kwargs = fake_client.audio.transcriptions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-4o-mini-transcribe")
        self.assertEqual(kwargs["language"], "pt")
        self.assertEqual(kwargs["prompt"], "pt-en music commands")
        self.assertEqual(kwargs["file"][0], "command.wav")
        self.assertEqual(kwargs["file"][1], b"RIFF-fake")

    def test_languages_list_when_configured(self):
        fake_result = MagicMock()
        fake_result.text = "play hello"
        fake_result.usage = None

        fake_client = MagicMock()
        fake_client.audio.transcriptions.create.return_value = fake_result

        env = {"OPENAI_STT_LANGUAGES": "pt,en", "OPENAI_STT_LANGUAGE": "pt"}
        with patch.dict("os.environ", env, clear=False):
            with patch("openai.OpenAI", return_value=fake_client):
                result = transcribe_audio(b"x", api_key="sk-test", prompt="p")

        self.assertEqual(result.text, "play hello")
        self.assertIsNone(result.input_tokens)
        kwargs = fake_client.audio.transcriptions.create.call_args.kwargs
        self.assertEqual(kwargs["languages"], ["pt", "en"])
        self.assertNotIn("language", kwargs)

    def test_wraps_api_errors(self):
        fake_client = MagicMock()
        fake_client.audio.transcriptions.create.side_effect = RuntimeError(
            "boom"
        )

        with patch("openai.OpenAI", return_value=fake_client):
            with self.assertRaises(TranscriptionError) as ctx:
                transcribe_audio(b"x", api_key="sk-test")

        self.assertIn("falha na transcricao OpenAI", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
