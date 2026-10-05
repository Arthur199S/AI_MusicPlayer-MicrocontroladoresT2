"""Loop principal do tocador de musica."""

import os

from dotenv import load_dotenv

from .command_parser import parse_command
from .openai_transcribe import TranscriptionError, transcribe_audio
from .player import Player, PlayerError
from .speaker_beep import SpeakerBeep, SpeakerBeepError
from .voice_recognition import VoiceRecognitionError, VoiceRecognizer
from .youtube_search import YouTubeSearchError, find_audio_url


def respond(message: str) -> None:
    print(f"AI Music Player: {message}", flush=True)


def run() -> None:
    load_dotenv()

    model_path = os.environ.get("VOSK_MODEL_PATH", "models/vosk-model-small-pt-0.3")
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        respond(
            "Defina OPENAI_API_KEY no arquivo .env (veja .env.example) "
            "antes de iniciar."
        )
        return

    try:
        recognizer = VoiceRecognizer(model_path)
    except VoiceRecognitionError as error:
        respond(str(error))
        return

    beep = None
    try:
        beep = SpeakerBeep()
    except SpeakerBeepError as error:
        respond(f"Bip de speaker indisponivel ({error}). Seguindo sem bip.")

    player = Player()
    respond(
        f"Pronto. Microfone: {recognizer.device_name} "
        f"({recognizer.device_sample_rate} Hz, ganho x{recognizer.mic_gain:g})."
    )
    if beep is not None:
        respond(f"Feedback: alto-falante ({beep.device_name}).")
    respond(f"Musica: mpv audio-device={player.audio_device}")
    respond(
        'Diga a wake word ("assistente" / "jarvis") e em seguida o comando. '
        'Ex.: "assistente, toque evidencias".'
    )
    try:
        while True:
            respond("Aguardando wake word...")
            wake_text = recognizer.listen_for_wake()
            if not wake_text:
                continue

            if beep is not None:
                try:
                    beep.beep(count=1)
                except SpeakerBeepError as error:
                    respond(f"Falha no bip: {error}")

            respond(f"Ativado ({wake_text}). Fale o comando...")
            clip = recognizer.record_command_clip()
            if not clip:
                respond("Nao ouvi o comando. Tente de novo.")
                continue

            try:
                text = transcribe_audio(clip)
            except TranscriptionError as error:
                respond(str(error))
                continue

            if not text:
                respond("Nao entendi o audio. Fale mais perto / mais alto.")
                continue

            respond(f"Ouvi: {text}")
            command = parse_command(text)
            action = command["action"]

            if action == "aguardar":
                respond("Estou ouvindo. Diga o comando apos a wake word.")
                continue
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
                respond(
                    'Nao entendi o comando. Ex.: "toque evidencias", '
                    '"pause", "pare".'
                )
    except KeyboardInterrupt:
        respond("Encerrando.")
    finally:
        player.stop()
        if beep is not None:
            beep.close()


if __name__ == "__main__":
    run()
