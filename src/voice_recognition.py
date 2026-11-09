"""Captura de audio: wake word local (Vosk) e clip para STT na nuvem."""

from __future__ import annotations

import array
import io
import json
import os
import queue
import time
import wave

from .command_parser import contains_wake_word


class VoiceRecognitionError(RuntimeError):
    """Indica que o reconhecimento de voz nao pode ser iniciado."""


# Palavras no vocabulario do modelo PT pequeno (jarvis/assistencia nao existem).
_WAKE_GRAMMAR_WORDS = (
    "assistente",
    "jarbas",
)


def _to_mono(samples: array.array, channels: int) -> array.array:
    if channels <= 1:
        return samples
    mono = array.array("h")
    for i in range(0, len(samples), channels):
        frame = samples[i : i + channels]
        mono.append(sum(frame) // len(frame))
    return mono


def _amplify(samples: array.array, gain: float) -> array.array:
    amplified = array.array("h")
    for sample in samples:
        value = int(sample * gain)
        if value > 32767:
            value = 32767
        elif value < -32768:
            value = -32768
        amplified.append(value)
    return amplified


def _downsample(samples: array.array, factor: int) -> array.array:
    if factor <= 1:
        return samples
    return array.array("h", samples[::factor])


def _prepare_pcm(pcm: bytes, channels: int, factor: int, gain: float) -> bytes:
    samples = array.array("h")
    samples.frombytes(pcm)
    samples = _to_mono(samples, channels)
    samples = _amplify(samples, gain)
    samples = _downsample(samples, factor)
    return samples.tobytes()


def _pcm_to_wav(pcm: bytes, sample_rate: int, channels: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    return buffer.getvalue()


def _block_peak(pcm: bytes) -> int:
    samples = array.array("h")
    samples.frombytes(pcm)
    return max((abs(sample) for sample in samples), default=0)


class VoiceRecognizer:
    def __init__(
        self,
        model_path: str,
        sample_rate: int = 16_000,
        mic_gain: float | None = None,
    ) -> None:
        try:
            import sounddevice as sounddevice
            from vosk import KaldiRecognizer, Model
        except ImportError as error:
            raise VoiceRecognitionError(
                "instale as dependencias de audio com 'pip install -r requirements.txt'"
            ) from error

        self._sounddevice = sounddevice
        self._recognizer_type = KaldiRecognizer
        self._model = Model(model_path)
        self.sample_rate = sample_rate
        if mic_gain is None:
            mic_gain = float(os.environ.get("MIC_GAIN", "10"))
        self.mic_gain = mic_gain
        # Blocos menores = partials do Vosk mais rapidos (padrao ~80 ms).
        self.block_ms = float(os.environ.get("WAKE_BLOCK_MS", "80"))
        # Gate de energia: ignora ruido de fundo abaixo do piso adaptativo.
        self.wake_energy_factor = float(os.environ.get("WAKE_ENERGY_FACTOR", "2.2"))
        self.min_speech_peak = int(os.environ.get("MIN_SPEECH_PEAK", "350"))

        device = sounddevice.query_devices(kind="input")
        self.device_name = device["name"]
        self.device_sample_rate = int(device["default_samplerate"])
        # VoiceHAT costuma ter sinal so no canal 0; preferir mono.
        self.channels = 1
        if self.device_sample_rate % self.sample_rate != 0:
            raise VoiceRecognitionError(
                f"taxa do microfone ({self.device_sample_rate} Hz) "
                f"nao e multipla da taxa do Vosk ({self.sample_rate} Hz)"
            )
        self._downsample_factor = self.device_sample_rate // self.sample_rate
        self._wake_grammar = json.dumps([*_WAKE_GRAMMAR_WORDS, "[unk]"])

    def _open_input(self, audio_queue: queue.Queue[bytes]):
        def callback(indata, frames, callback_time, status) -> None:
            del frames, callback_time, status
            audio_queue.put(bytes(indata))

        blocksize = max(int(self.device_sample_rate * self.block_ms / 1000.0), 1024)
        return self._sounddevice.RawInputStream(
            samplerate=self.device_sample_rate,
            blocksize=blocksize,
            dtype="int16",
            channels=self.channels,
            callback=callback,
        )

    def _prepare_for_vosk(self, pcm: bytes) -> bytes:
        return _prepare_pcm(
            pcm, self.channels, self._downsample_factor, self.mic_gain
        )

    def _make_wake_recognizer(self):
        """Reconhecedor com vocabulario fechado — mais rapido e menos ruido."""
        return self._recognizer_type(
            self._model, self.sample_rate, self._wake_grammar
        )

    def listen_once(self, timeout: float = 8.0) -> str:
        """Aguarda uma frase e retorna o texto reconhecido pelo Vosk."""
        audio_queue: queue.Queue[bytes] = queue.Queue()
        recognizer = self._recognizer_type(self._model, self.sample_rate)
        peak = 0

        started = time.monotonic()
        with self._open_input(audio_queue):
            while time.monotonic() - started < timeout:
                try:
                    data = audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                prepared = self._prepare_for_vosk(data)
                peak = max(peak, _block_peak(prepared))
                if recognizer.AcceptWaveform(prepared):
                    result = json.loads(recognizer.Result()).get("text", "")
                    if result and result.strip() != "[unk]":
                        return result

        text = json.loads(recognizer.FinalResult()).get("text", "")
        if text.strip() == "[unk]":
            text = ""
        if not text and peak < self.min_speech_peak:
            return ""
        return text

    def listen_for_wake(
        self,
        timeout: float | None = None,
        stop_event: object | None = None,
    ) -> str:
        """Escuta ate detectar uma wake word via Vosk.

        Usa gramatica fechada (assistente/jarbas) para responder mais rapido
        e ignorar conversa/ruido de fundo. Retorna o trecho com a wake word.
        Se ``timeout`` for None, espera indefinidamente.
        Se ``stop_event`` estiver setado, retorna string vazia.
        """
        audio_queue: queue.Queue[bytes] = queue.Queue()
        recognizer = self._make_wake_recognizer()
        started = time.monotonic()
        # Piso de ruido adaptativo (pico apos ganho).
        noise_floor = 200.0
        last_reset = started

        with self._open_input(audio_queue):
            while True:
                if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
                    return ""
                if timeout is not None and time.monotonic() - started >= timeout:
                    return ""

                try:
                    data = audio_queue.get(timeout=0.25)
                except queue.Empty:
                    continue

                prepared = self._prepare_for_vosk(data)
                peak = _block_peak(prepared)

                # Atualiza piso so com blocos "quietos"; evita subir com a fala.
                if peak < noise_floor * 1.5:
                    noise_floor = (0.95 * noise_floor) + (0.05 * max(peak, 1))

                gate = max(noise_floor * self.wake_energy_factor, float(self.min_speech_peak))
                if peak < gate:
                    # Ainda alimenta silencio curto para o Vosk fechar endpoint;
                    # reset periodico evita acumular [unk] de ruido.
                    if time.monotonic() - last_reset > 4.0:
                        recognizer = self._make_wake_recognizer()
                        last_reset = time.monotonic()
                    continue

                if recognizer.AcceptWaveform(prepared):
                    text = json.loads(recognizer.Result()).get("text", "")
                    last_reset = time.monotonic()
                    if text and text.strip() != "[unk]" and contains_wake_word(text):
                        return text
                else:
                    partial = json.loads(recognizer.PartialResult()).get(
                        "partial", ""
                    )
                    if partial and contains_wake_word(partial):
                        return partial

    def record_command_clip(
        self,
        max_duration: float = 8.0,
        silence_timeout: float | None = None,
        speech_threshold: int | None = None,
    ) -> bytes:
        """Grava um clip WAV mono 16 kHz apos a wake word.

        Encerra no silencio apos ter ouvido fala, ou em ``max_duration``.
        Retorna bytes WAV (pode ser vazio se nao houver sinal util).
        """
        if silence_timeout is None:
            silence_timeout = float(os.environ.get("COMMAND_SILENCE_TIMEOUT", "1.0"))
        if speech_threshold is None:
            # Pico apos ganho (nao no PCM cru do mic).
            speech_threshold = int(os.environ.get("SPEECH_THRESHOLD", "2800"))

        audio_queue: queue.Queue[bytes] = queue.Queue()
        prepared_chunks: list[bytes] = []
        peak = 0
        heard_speech = False
        last_voice = time.monotonic()
        started = time.monotonic()
        # Pequeno pre-roll: nao descartar o inicio do comando.
        preroll_until = started + 0.35

        with self._open_input(audio_queue):
            while time.monotonic() - started < max_duration:
                try:
                    data = audio_queue.get(timeout=0.2)
                except queue.Empty:
                    if (
                        heard_speech
                        and time.monotonic() - last_voice >= silence_timeout
                        and time.monotonic() > preroll_until
                    ):
                        break
                    continue

                prepared = self._prepare_for_vosk(data)
                block_peak = _block_peak(prepared)
                peak = max(peak, block_peak)
                prepared_chunks.append(prepared)

                if block_peak >= speech_threshold:
                    heard_speech = True
                    last_voice = time.monotonic()
                elif (
                    heard_speech
                    and time.monotonic() - last_voice >= silence_timeout
                    and time.monotonic() > preroll_until
                ):
                    break

        if peak < self.min_speech_peak or not prepared_chunks:
            return b""

        pcm = b"".join(prepared_chunks)
        return _pcm_to_wav(pcm, self.sample_rate, channels=1)
