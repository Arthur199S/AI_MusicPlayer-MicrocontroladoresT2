import unittest

from src.command_parser import parse_command


class CommandParserTests(unittest.TestCase):
    def test_extracts_music_query(self):
        self.assertEqual(
            parse_command("Quero tocar Evidencias do Chitaozinho e Xororo"),
            {"action": "tocar", "query": "evidencias do chitaozinho e xororo"},
        )

    def test_recognizes_control_commands(self):
        self.assertEqual(parse_command("Pause a musica"), {"action": "pausar"})
        self.assertEqual(parse_command("Pode continuar"), {"action": "continuar"})
        self.assertEqual(parse_command("Pare"), {"action": "parar"})
        self.assertEqual(parse_command("Toque a proxima"), {"action": "proxima"})

    def test_unknown_command(self):
        self.assertEqual(parse_command("bom dia"), {"action": "desconhecido"})


if __name__ == "__main__":
    unittest.main()
