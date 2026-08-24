"""Loop principal do tocador de musica."""

import os

from .command_parser import parse_command
from .player import Player, PlayerError
from .voice_recognition import VoiceRecognitionError, VoiceRecognizer
from .youtube_search import YouTubeSearchError, find_audio_url


def respond(message: str) -> None:
    print(f"AI Music Player: {message}")


def run() -> None:
    model_path = os.environ.get("VOSK_MODEL_PATH", "models/vosk-model-small-pt-0.3")
    try:
        recognizer = VoiceRecognizer(model_path)
    except VoiceRecognitionError as error:
        respond(str(error))
        return

    player = Player()
    respond("Pronto. Fale um comando.")
    try:
        while True:
            text = recognizer.listen_once()
            if not text:
                respond("Nao entendi o comando.")
                continue
            command = parse_command(text)
            action = command["action"]

            if action == "tocar":
                respond(f"Buscando: {command['query']}")
                try:
                    player.play(find_audio_url(command["query"]))
                    respond("Reproducao iniciada.")
                except (PlayerError, YouTubeSearchError) as error:
                    respond(str(error))
            elif action == "pausar":
                player.pause()
                respond("Reproducao pausada.")
            elif action == "continuar":
                player.resume()
                respond("Reproducao retomada.")
            elif action == "proxima":
                player.next()
                respond("Avancando para a proxima musica.")
            elif action == "parar":
                player.stop()
                respond("Reproducao parada.")
            else:
                respond("Comando desconhecido.")
    except KeyboardInterrupt:
        respond("Encerrando.")
    finally:
        player.stop()


if __name__ == "__main__":
    run()
