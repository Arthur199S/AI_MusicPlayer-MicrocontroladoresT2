"""Captura de uma frase usando Vosk e sounddevice."""

import json
import queue
import time


class VoiceRecognitionError(RuntimeError):
    """Indica que o reconhecimento de voz nao pode ser iniciado."""


class VoiceRecognizer:
    def __init__(self, model_path: str, sample_rate: int = 16_000) -> None:
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

    def listen_once(self, timeout: float = 10.0) -> str:
        """Aguarda uma frase e retorna o texto reconhecido."""
        audio_queue: queue.Queue[bytes] = queue.Queue()
        recognizer = self._recognizer_type(self._model, self.sample_rate)

        def callback(indata, frames, callback_time, status) -> None:
            del frames, callback_time, status
            audio_queue.put(bytes(indata))

        started = time.monotonic()
        with self._sounddevice.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=8_000,
            dtype="int16",
            channels=1,
            callback=callback,
        ):
            while time.monotonic() - started < timeout:
                try:
                    data = audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result()).get("text", "")
                    if result:
                        return result

        return json.loads(recognizer.FinalResult()).get("text", "")
