"""Buzzer no Voice HAT (P2 / Driver 2 = BCM GPIO 27 por padrao)."""

from __future__ import annotations

import os
import sys
import time


# Voice HAT: Driver 2 Breakout = physical pin 13 = BCM GPIO 27
DEFAULT_BUZZER_GPIO = 27
DEFAULT_BUZZER_MODE = "tone"  # passive piezo precisa de frequencia
DEFAULT_BUZZER_FREQ_HZ = 2000

# No Raspberry Pi OS o lgpio costuma vir do apt (python3-lgpio),
# nao do pip dentro do venv.
_SYSTEM_DIST_PACKAGES = "/usr/lib/python3/dist-packages"


class BuzzerError(RuntimeError):
    """Falha ao acessar o GPIO do buzzer."""


def _import_lgpio():
    try:
        import lgpio

        return lgpio
    except ImportError:
        if _SYSTEM_DIST_PACKAGES not in sys.path:
            sys.path.append(_SYSTEM_DIST_PACKAGES)
        try:
            import lgpio

            return lgpio
        except ImportError as error:
            raise BuzzerError(
                "instale o pacote do sistema: sudo apt install -y python3-lgpio"
            ) from error


def _resolve_mode(mode: str | None) -> str:
    resolved = (mode or os.environ.get("BUZZER_MODE", "") or DEFAULT_BUZZER_MODE)
    resolved = resolved.strip().lower()
    if resolved not in {"tone", "active"}:
        raise BuzzerError("BUZZER_MODE deve ser 'tone' ou 'active'")
    return resolved


class Buzzer:
    """Controla buzzer no Driver/Servo breakout do Voice HAT.

    - ``tone`` (padrao): PWM ~2 kHz — funciona com piezo passivo.
    - ``active``: nivel DC alto/baixo — so para buzzer ativo com oscilador.
    """

    def __init__(
        self,
        pin: int | None = None,
        active_high: bool = True,
        mode: str | None = None,
        frequency_hz: int | None = None,
    ) -> None:
        if pin is None:
            env = os.environ.get("BUZZER_GPIO", "").strip()
            pin = int(env) if env else DEFAULT_BUZZER_GPIO
        if frequency_hz is None:
            env_freq = os.environ.get("BUZZER_FREQ_HZ", "").strip()
            frequency_hz = int(env_freq) if env_freq else DEFAULT_BUZZER_FREQ_HZ

        self.pin = pin
        self.active_high = active_high
        self.mode = _resolve_mode(mode)
        self.frequency_hz = frequency_hz
        self._handle = None

        self._lgpio = _import_lgpio()
        try:
            self._handle = self._lgpio.gpiochip_open(0)
            self._lgpio.gpio_claim_output(self._handle, self.pin)
            self.off()
        except BuzzerError:
            raise
        except Exception as error:  # noqa: BLE001
            self.close()
            raise BuzzerError(
                f"nao foi possivel abrir GPIO {self.pin}: {error}"
            ) from error

    def _level_on(self) -> int:
        return 1 if self.active_high else 0

    def _level_off(self) -> int:
        return 0 if self.active_high else 1

    def on(self) -> None:
        if self._handle is None:
            raise BuzzerError("buzzer ja foi fechado")
        if self.mode == "tone":
            # duty 50% gera tom audivel no piezo passivo
            self._lgpio.tx_pwm(
                self._handle, self.pin, self.frequency_hz, 50.0
            )
        else:
            self._lgpio.gpio_write(self._handle, self.pin, self._level_on())

    def off(self) -> None:
        if self._handle is None:
            return
        if self.mode == "tone":
            try:
                self._lgpio.tx_pwm(self._handle, self.pin, 0, 0)
            except Exception:  # noqa: BLE001
                pass
        self._lgpio.gpio_write(self._handle, self.pin, self._level_off())

    def beep(
        self,
        duration: float = 0.15,
        count: int = 1,
        gap: float = 0.08,
    ) -> None:
        """Emite um ou mais bips curtos."""
        for index in range(count):
            self.on()
            time.sleep(duration)
            self.off()
            if index + 1 < count:
                time.sleep(gap)

    def close(self) -> None:
        if self._handle is not None:
            try:
                self.off()
            except Exception:  # noqa: BLE001
                pass
            try:
                self._lgpio.gpiochip_close(self._handle)
            except Exception:  # noqa: BLE001
                pass
            self._handle = None

    def __enter__(self) -> Buzzer:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        self.close()

    def __del__(self) -> None:
        self.close()
