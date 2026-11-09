"""Motor de voz start/stop (thread) controlado pelo dashboard."""

from __future__ import annotations

import os
import threading
from typing import Callable

from .app_state import AppState
from .command_parser import parse_command
from .openai_transcribe import TranscriptionError, transcribe_audio
from .player import Player, PlayerError
from .speaker_beep import SpeakerBeep, SpeakerBeepError
from .voice_recognition import VoiceRecognitionError, VoiceRecognizer
from .youtube_search import YouTubeSearchError, find_audio_url


RespondFn = Callable[[str], None]


class VoiceEngine:
    """Executa o loop wake/STT/player em uma thread dedicada."""

    def __init__(
        self,
        state: AppState,
        player: Player,
        *,
        respond: RespondFn | None = None,
    ) -> None:
        self.state = state
        self.player = player
        self._respond = respond or (lambda message: print(f"AI Music Player: {message}", flush=True))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._recognizer: VoiceRecognizer | None = None
        self._beep: SpeakerBeep | None = None

    @property
    def running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self) -> bool:
        """Inicia o motor. Retorna False se ja estiver rodando."""
        with self._lock:
            if self.running:
                return False
            self._stop.clear()
            self.state.set_engine_running(True)
            self.state.set_status("starting")
            self._thread = threading.Thread(
                target=self._run_loop,
                name="voice-engine",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self, *, stop_audio: bool = True) -> None:
        """Pede parada do motor (nao derruba o dashboard)."""
        self._stop.set()
        with self._lock:
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=8.0)
        if stop_audio:
            try:
                self.player.stop()
            except PlayerError:
                pass
            self.state.clear_current_track(stopped=True)
        self.state.set_engine_running(False)
        self.state.set_status("stopped")
        self.state.log("Motor de voz parado.")

    def _run_loop(self) -> None:
        model_path = os.environ.get("VOSK_MODEL_PATH", "models/vosk-model-small-pt-0.3")
        try:
            recognizer = VoiceRecognizer(model_path)
        except VoiceRecognitionError as error:
            self.state.set_status("error")
            self.state.log(str(error))
            self._respond(str(error))
            self.state.set_engine_running(False)
            return

        self._recognizer = recognizer
        self.state.mic_name = (
            f"{recognizer.device_name} ({recognizer.device_sample_rate} Hz, "
            f"ganho x{recognizer.mic_gain:g})"
        )
        self.state.audio_device = self.player.audio_device

        beep = None
        try:
            beep = SpeakerBeep()
        except SpeakerBeepError as error:
            self._respond(f"Bip de speaker indisponivel ({error}). Seguindo sem bip.")
            self.state.log(f"Bip indisponivel: {error}")
        self._beep = beep

        self._respond(
            f"Pronto. Microfone: {recognizer.device_name} "
            f"({recognizer.device_sample_rate} Hz, ganho x{recognizer.mic_gain:g}, "
            f"bloco {recognizer.block_ms:g} ms, wake=grammar)."
        )
        if beep is not None:
            self._respond(f"Feedback: alto-falante ({beep.device_name}).")
        self._respond(f"Musica: mpv audio-device={self.player.audio_device}")
        self._respond(
            'Diga a wake word ("assistente" / "jarvis") e em seguida o comando. '
            'Ex.: "assistente, toque evidencias".'
        )
        self.state.log("Motor de voz iniciado.")

        try:
            while not self._stop.is_set():
                self.state.set_status("listening_wake")
                self._respond("Aguardando wake word...")
                wake_text = recognizer.listen_for_wake(
                    timeout=2.0,
                    stop_event=self._stop,
                )
                if self._stop.is_set():
                    break
                if not wake_text:
                    continue

                self.state.set_wake(wake_text)
                if beep is not None:
                    try:
                        beep.beep(count=1)
                    except SpeakerBeepError as error:
                        self._respond(f"Falha no bip: {error}")

                self._respond(f"Ativado ({wake_text}). Fale o comando...")
                self.state.set_status("recording")
                clip = recognizer.record_command_clip()
                if self._stop.is_set():
                    break
                if not clip:
                    self._respond("Nao ouvi o comando. Tente de novo.")
                    self.state.log("Clip vazio apos wake.")
                    continue

                self.state.set_status("transcribing")
                try:
                    result = transcribe_audio(clip)
                except TranscriptionError as error:
                    self._respond(str(error))
                    self.state.log(str(error))
                    continue

                self.state.record_stt(
                    result.text,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    total_tokens=result.total_tokens,
                    audio_seconds=result.audio_seconds,
                )

                if not result.text:
                    self._respond("Nao entendi o audio. Fale mais perto / mais alto.")
                    continue

                self._respond(f"Ouvi: {result.text}")
                self.state.log(f"Ouvi: {result.text}")
                command = parse_command(result.text)
                action = command["action"]
                self.state.set_action(action)
                self._handle_action(action, command)
        finally:
            if beep is not None:
                beep.close()
            self.state.set_engine_running(False)
            if not self._stop.is_set():
                self.state.set_status("stopped")

    def _handle_action(self, action: str, command: dict[str, str]) -> None:
        if action == "aguardar":
            self._respond("Estou ouvindo. Diga o comando apos a wake word.")
            return
        if action == "tocar":
            query = command["query"]
            self._respond(f"Buscando: {query}")
            try:
                self.player.play(find_audio_url(query))
                self.state.set_playing(query)
                self._respond("Reproducao iniciada.")
                self.state.log(f"Tocando: {query}")
            except (PlayerError, YouTubeSearchError) as error:
                self._respond(str(error))
                self.state.log(str(error))
            return
        if action == "pausar":
            self.player.pause()
            self.state.clear_current_track(paused=True)
            self._respond("Reproducao pausada.")
            return
        if action == "continuar":
            self.player.resume()
            self.state.set_status("playing")
            self._respond("Reproducao retomada.")
            return
        if action == "proxima":
            self.player.next()
            self._respond("Avancando para a proxima musica.")
            return
        if action == "parar":
            self.player.stop()
            self.state.clear_current_track(stopped=True)
            self._respond("Reproducao parada.")
            return

        self._respond(
            'Nao entendi o comando. Ex.: "toque evidencias", "pause", "pare".'
        )
