"""Captura de audio: wake word local (Vosk) e clip para STT na nuvem."""

from __future__ import annotations

import array
import io
import json
import queue
import time
import wave

from .command_parser import contains_wake_word


class VoiceRecognitionError(RuntimeError):
    """Indica que o reconhecimento de voz nao pode ser iniciado."""


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
        mic_gain: float = 12.0,
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
        self.mic_gain = mic_gain

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

    def _open_input(self, audio_queue: queue.Queue[bytes]):
        def callback(indata, frames, callback_time, status) -> None:
            del frames, callback_time, status
            audio_queue.put(bytes(indata))

        blocksize = max(self.device_sample_rate // 4, 1024)
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

                peak = max(peak, _block_peak(data))
                prepared = self._prepare_for_vosk(data)
                if recognizer.AcceptWaveform(prepared):
                    result = json.loads(recognizer.Result()).get("text", "")
                    if result:
                        return result

        text = json.loads(recognizer.FinalResult()).get("text", "")
        if not text and peak < 500:
            return ""
        return text

    def listen_for_wake(self, timeout: float | None = None) -> str:
        """Escuta ate detectar uma wake word via Vosk.

        Retorna o trecho de texto em que a wake word apareceu.
        Se ``timeout`` for None, espera indefinidamente.
        """
        audio_queue: queue.Queue[bytes] = queue.Queue()
        recognizer = self._recognizer_type(self._model, self.sample_rate)
        started = time.monotonic()

        with self._open_input(audio_queue):
            while True:
                if timeout is not None and time.monotonic() - started >= timeout:
                    return ""

                try:
                    data = audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                prepared = self._prepare_for_vosk(data)
                if recognizer.AcceptWaveform(prepared):
                    text = json.loads(recognizer.Result()).get("text", "")
                    if text and contains_wake_word(text):
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
        silence_timeout: float = 1.2,
        speech_threshold: int = 800,
    ) -> bytes:
        """Grava um clip WAV mono 16 kHz apos a wake word.

        Encerra no silencio apos ter ouvido fala, ou em ``max_duration``.
        Retorna bytes WAV (pode ser vazio se nao houver sinal util).
        """
        audio_queue: queue.Queue[bytes] = queue.Queue()
        prepared_chunks: list[bytes] = []
        peak = 0
        heard_speech = False
        last_voice = time.monotonic()
        started = time.monotonic()

        with self._open_input(audio_queue):
            while time.monotonic() - started < max_duration:
                try:
                    data = audio_queue.get(timeout=0.3)
                except queue.Empty:
                    if heard_speech and time.monotonic() - last_voice >= silence_timeout:
                        break
                    continue

                block_peak = _block_peak(data)
                peak = max(peak, block_peak)
                prepared = self._prepare_for_vosk(data)
                prepared_chunks.append(prepared)

                if block_peak >= speech_threshold:
                    heard_speech = True
                    last_voice = time.monotonic()
                elif heard_speech and time.monotonic() - last_voice >= silence_timeout:
                    break

        if peak < 500 or not prepared_chunks:
            return b""

        pcm = b"".join(prepared_chunks)
        return _pcm_to_wav(pcm, self.sample_rate, channels=1)
