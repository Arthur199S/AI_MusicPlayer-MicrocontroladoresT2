import unittest
from unittest.mock import MagicMock, patch

from src.youtube_search import AudioResult, YouTubeSearchError, find_audio, find_audio_url


class FindAudioTests(unittest.TestCase):
    def test_parses_title_and_url(self):
        fake = MagicMock()
        fake.stdout = "Evidencias - Chitaozinho e Xororo\nhttps://example.com/audio.m4a\n"
        with patch("src.youtube_search.shutil.which", return_value="/usr/bin/yt-dlp"):
            with patch("src.youtube_search.subprocess.run", return_value=fake) as run:
                result = find_audio("evidencias")
        self.assertIsInstance(result, AudioResult)
        self.assertEqual(result.title, "Evidencias - Chitaozinho e Xororo")
        self.assertEqual(result.url, "https://example.com/audio.m4a")
        self.assertEqual(result.query, "evidencias")
        cmd = run.call_args.args[0]
        self.assertIn("--print", cmd)
        self.assertIn("%(title)s", cmd)
        self.assertIn("%(url)s", cmd)

    def test_find_audio_url_compat(self):
        fake = MagicMock()
        fake.stdout = "Titulo\nhttps://x/y\n"
        with patch("src.youtube_search.shutil.which", return_value="/usr/bin/yt-dlp"):
            with patch("src.youtube_search.subprocess.run", return_value=fake):
                self.assertEqual(find_audio_url("x"), "https://x/y")

    def test_empty_query(self):
        with self.assertRaises(YouTubeSearchError):
            find_audio("  ")


if __name__ == "__main__":
    unittest.main()
