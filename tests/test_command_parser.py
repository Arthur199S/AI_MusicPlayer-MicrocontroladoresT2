import unittest

from src.command_parser import parse_command


class CommandParserTests(unittest.TestCase):
    def test_extracts_music_query(self):
        self.assertEqual(
            parse_command("Jarvis toque Evidencias do Chitaozinho e Xororo"),
            {"action": "tocar", "query": "evidencias do chitaozinho e xororo"},
        )

    def test_works_without_wake_word(self):
        self.assertEqual(
            parse_command("toque evidencias"),
            {"action": "tocar", "query": "evidencias"},
        )

    def test_strips_musica_prefix(self):
        self.assertEqual(
            parse_command("Assistente toque uma musica Bohemian Rhapsody"),
            {"action": "tocar", "query": "bohemian rhapsody"},
        )

    def test_recognizes_control_commands(self):
        self.assertEqual(parse_command("Jarvis pause a musica"), {"action": "pausar"})
        self.assertEqual(parse_command("pode continuar"), {"action": "continuar"})
        self.assertEqual(parse_command("pare"), {"action": "parar"})
        self.assertEqual(parse_command("toque a proxima"), {"action": "proxima"})

    def test_wake_word_only(self):
        self.assertEqual(parse_command("Jarvis"), {"action": "aguardar"})

    def test_unknown_command(self):
        self.assertEqual(parse_command("bom dia"), {"action": "desconhecido"})


if __name__ == "__main__":
    unittest.main()
