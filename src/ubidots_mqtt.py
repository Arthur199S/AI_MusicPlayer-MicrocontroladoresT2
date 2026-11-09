"""Ponte MQTT bidirecional com Ubidots STEM."""

from __future__ import annotations

import json
import os
import ssl
import threading
import time
from typing import Any, Callable

from .app_state import AppState
from .player import Player, PlayerError
from .system_metrics import system_metrics


RespondFn = Callable[[str], None]

# Cada valor publicado = 1 dot na cota do Ubidots. Para nao estourar o limite:
# - EVENT_KEYS so sobem quando o valor muda;
# - PERIODIC_KEYS sobem juntos a cada UBIDOTS_PUBLISH_INTERVAL (padrao 300 s).
EVENT_KEYS = (
    "app_status",
    "now_playing",
    "tracks_today",
    "engine_running",
    "stt_latency_ms",
    "e2e_latency_ms",
)
PERIODIC_KEYS = ("cpu_percent", "temp_c", "ram_percent", "heartbeat", "seconds_left")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def _parse_lv(payload: bytes | bytearray | str) -> float | None:
    try:
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else str(payload)
        return float(text.strip())
    except (AttributeError, TypeError, ValueError):
        return None


class UbidotsMqttBridge:
    """Publica telemetria e escuta cmd_pause / cmd_resume."""

    def __init__(
        self,
        state: AppState,
        player: Player,
        *,
        engine: Any | None = None,
        respond: RespondFn | None = None,
    ) -> None:
        self.state = state
        self.player = player
        self.engine = engine
        self._respond = respond or (lambda message: None)
        self._client: Any | None = None
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._running = False
        self._last_sent: dict[str, str] = {}
        self._last_publish_at: float = 0.0
        self._last_synced_paused: bool | None = None
        self._poll_interval = 2.0

        self.token = os.environ.get("UBIDOTS_TOKEN", "").strip()
        self.device_label = (
            os.environ.get("UBIDOTS_DEVICE_LABEL", "ai-music-player").strip().lower()
            or "ai-music-player"
        )
        self.host = (
            os.environ.get("UBIDOTS_MQTT_HOST", "industrial.api.ubidots.com").strip()
            or "industrial.api.ubidots.com"
        )
        self.port = int(os.environ.get("UBIDOTS_MQTT_PORT", "1883"))
        self.use_tls = _env_bool("UBIDOTS_MQTT_TLS", False)
        self.publish_interval = float(os.environ.get("UBIDOTS_PUBLISH_INTERVAL", "300"))
        if self.publish_interval < 30:
            self.publish_interval = 30.0

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.device_label)

    @property
    def connected(self) -> bool:
        client = self._client
        if client is None or not self._running:
            return False
        try:
            return bool(client.is_connected())
        except Exception:  # noqa: BLE001
            return False

    def start(self) -> bool:
        """Conecta ao broker. Retorna False se desabilitado ou sem dependencia."""
        if not self.enabled:
            self._respond(
                "Ubidots MQTT desligado (defina UBIDOTS_TOKEN e UBIDOTS_DEVICE_LABEL)."
            )
            return False
        try:
            from paho.mqtt import client as mqtt_client
        except ImportError:
            self._respond(
                "paho-mqtt nao instalado. Rode: pip install -r requirements.txt"
            )
            return False

        client_id = f"ai-music-{self.device_label}"
        try:
            client = mqtt_client.Client(
                mqtt_client.CallbackAPIVersion.VERSION2,
                client_id=client_id,
            )
        except (AttributeError, TypeError, ValueError):
            # paho-mqtt < 2.0
            client = mqtt_client.Client(client_id=client_id)

        client.username_pw_set(self.token, "")
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        if self.use_tls:
            client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
            if self.port == 1883:
                self.port = 8883

        try:
            client.connect(self.host, self.port, keepalive=60)
        except OSError as error:
            self._respond(f"Falha ao conectar Ubidots MQTT: {error}")
            return False

        self._client = client
        self._running = True
        client.loop_start()
        self._schedule_publish()
        self._respond(
            f"Ubidots MQTT conectado ({self.host}:{self.port}, device={self.device_label})."
        )
        return True

    def stop(self) -> None:
        self._running = False
        with self._lock:
            timer = self._timer
            self._timer = None
        if timer is not None:
            timer.cancel()
        client = self._client
        self._client = None
        if client is not None:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    def publish_now(self) -> None:
        """Publica telemetria imediatamente (se conectado)."""
        if not self._running or self._client is None:
            return
        payload = self.build_payload()
        for key in EVENT_KEYS:
            self._last_sent[key] = json.dumps(payload.get(key), sort_keys=True)
        self._last_publish_at = time.monotonic()
        self._send(payload)

    def publish_events(self) -> dict[str, Any]:
        """Publica so as variaveis de evento que MUDARAM (poucos dots)."""
        if not self._running or self._client is None:
            return {}
        payload = self.build_payload()
        changed: dict[str, Any] = {}
        for key in EVENT_KEYS:
            encoded = json.dumps(payload.get(key), sort_keys=True)
            if self._last_sent.get(key) != encoded:
                changed[key] = payload[key]
                self._last_sent[key] = encoded
        if not changed:
            return {}
        if "now_playing" in changed:
            changed["seconds_left"] = payload["seconds_left"]
        self._send(changed)
        return changed

    def _send(self, payload: dict[str, Any]) -> None:
        topic = f"/v1.6/devices/{self.device_label}"
        try:
            self._client.publish(topic, json.dumps(payload), qos=1)
        except Exception as error:  # noqa: BLE001
            self.state.log(f"Ubidots publish falhou: {error}")

    def build_payload(self) -> dict[str, Any]:
        snap = self.state.snapshot()
        sys_m = system_metrics()
        playback = self.player.playback_snapshot()
        engine_running = bool(snap.get("engine_running"))
        if self.engine is not None:
            engine_running = bool(getattr(self.engine, "running", False) or engine_running)

        track = str(snap.get("current_track") or "").strip()
        track_label = track if track else "nada tocando"
        # Nao depender so de app_status: o loop de voz volta a "listening_wake"
        # enquanto o mpv ainda toca. Preferir faixa atual + IPC do player.
        if not track:
            playing = 0
        elif playback.get("alive") and playback.get("paused") is True:
            playing = 0
        elif playback.get("alive"):
            playing = 1
        else:
            playing = 0 if snap.get("app_status") == "paused" else 1
        seconds_left = playback.get("seconds_left")
        if seconds_left is None:
            seconds_left = 0

        # Ubidots exige value numerico; o texto da faixa vai em context (string).
        payload: dict[str, Any] = {
            "app_status": snap.get("app_status_code", 0),
            "now_playing": {
                "value": playing,
                "context": {
                    "track": track_label,
                    "text": track_label,
                    "status": track_label,
                },
            },
            "tracks_today": snap.get("tracks_today", 0),
            "seconds_left": seconds_left,
            "cpu_percent": sys_m.get("cpu_percent") if sys_m.get("cpu_percent") is not None else 0,
            "temp_c": sys_m.get("temp_c") if sys_m.get("temp_c") is not None else 0,
            "ram_percent": sys_m.get("ram_percent") if sys_m.get("ram_percent") is not None else 0,
            "engine_running": 1 if engine_running else 0,
            "heartbeat": 1,
            "stt_latency_ms": snap.get("last_stt_latency_ms") or 0,
            "e2e_latency_ms": snap.get("last_e2e_latency_ms") or 0,
        }
        # IMPORTANTE: nao incluir cmd_pause/cmd_resume aqui. O broker devolve
        # ao Pi o que ele publica (eco), e isso causava loop de pause/resume.
        return payload

    def fetch_remote(self) -> dict[str, Any]:
        """Le do Ubidots (REST v2.0) o ultimo valor de cada variavel do device."""
        if not self.enabled:
            return {"enabled": False, "error": "UBIDOTS_TOKEN nao definido", "variables": {}}
        now = time.monotonic()
        cached = getattr(self, "_remote_cache", None)
        if cached is not None and now - cached[0] < 2.0:
            return cached[1]

        import urllib.error
        import urllib.request

        url = (
            f"https://industrial.api.ubidots.com/api/v2.0/devices/"
            f"~{self.device_label}/variables/?page_size=100"
        )
        request = urllib.request.Request(url, headers={"X-Auth-Token": self.token})
        result: dict[str, Any] = {"enabled": True, "error": None, "variables": {}}
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                data = json.loads(response.read().decode("utf-8"))
            for item in data.get("results", []):
                last = item.get("lastValue") or {}
                result["variables"][str(item.get("label"))] = {
                    "value": last.get("value"),
                    "timestamp": last.get("timestamp"),
                    "context": last.get("context") or {},
                }
        except (urllib.error.URLError, OSError, ValueError) as error:
            result["error"] = str(error)
        self._remote_cache = (now, result)
        return result

    def is_paused(self) -> bool:
        """True se a musica esta pausada (mpv se disponivel, senao estado)."""
        playback = self.player.playback_snapshot()
        if playback.get("alive") and isinstance(playback.get("paused"), bool):
            return bool(playback["paused"])
        return self.state.snapshot().get("app_status") == "paused"

    def handle_command(self, name: str, value: float) -> None:
        """Processa downlink cmd_pause / cmd_resume (idempotente a ecos).

        - cmd_pause=1 -> pausa (so se ainda nao estiver pausado)
        - cmd_pause=0 -> retoma (so se estiver pausado)
        - cmd_resume=1 -> retoma (so se estiver pausado)
        Ecos do que o proprio Pi publicou viram no-op.
        """
        if name == "cmd_pause":
            if value == 1:
                self._do_pause(source="Ubidots")
            elif value == 0:
                self._do_resume(source="Ubidots switch")
            return
        if name == "cmd_resume" and value == 1:
            self._do_resume(source="Ubidots")

    def _do_pause(self, *, source: str) -> None:
        if self.is_paused():
            self._sync_cmd_switches()
            return
        try:
            self.player.set_pause(True)
        except PlayerError as error:
            self.state.log(f"Pause via {source} falhou: {error}")
            return
        self.state.clear_current_track(paused=True)
        self.state.log(f"Pause via {source}.")
        self._sync_cmd_switches()
        self.publish_events()

    def _do_resume(self, *, source: str) -> None:
        if not self.is_paused():
            # Eco de cmd_pause=0 / botao resume sem estar pausado: so alinha o switch.
            self._sync_cmd_switches()
            return
        try:
            self.player.set_pause(False)
        except PlayerError as error:
            self.state.log(f"Resume via {source} falhou: {error}")
            return
        self.state.set_status("playing")
        self.state.log(f"Resume via {source}.")
        self._sync_cmd_switches()
        self.publish_events()

    def _sync_cmd_switches(self, *, force: bool = False) -> None:
        """Alinha switches no Ubidots: cmd_pause=1 so pausado; cmd_resume=0.

        So publica quando o estado mudou (evita flood e loops de eco).
        """
        if self._client is None:
            return
        paused = self.state.snapshot().get("app_status") == "paused"
        if not force and paused == self._last_synced_paused:
            return
        self._last_synced_paused = paused
        topic = f"/v1.6/devices/{self.device_label}"
        try:
            self._client.publish(
                topic,
                json.dumps({"cmd_pause": 1 if paused else 0, "cmd_resume": 0}),
                qos=1,
            )
        except Exception as error:  # noqa: BLE001
            self.state.log(f"Ubidots sync cmd_* falhou: {error}")

    def _schedule_publish(self) -> None:
        if not self._running:
            return

        def _tick() -> None:
            if not self._running:
                return
            try:
                now = time.monotonic()
                due = (now - self._last_publish_at) >= self.publish_interval
                if due or self._last_publish_at == 0.0:
                    self.publish_now()  # tudo junto (saude + eventos)
                else:
                    self.publish_events()  # so o que mudou
                # Pausou por voz/dashboard local? Alinha o switch do Ubidots.
                self._sync_cmd_switches()
            finally:
                self._schedule_publish()

        with self._lock:
            self._timer = threading.Timer(self._poll_interval, _tick)
            self._timer.daemon = True
            self._timer.start()

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
        # Compativel com API v1 (rc int) e v2 (reason_code object).
        rc = getattr(reason_code, "value", reason_code)
        if rc not in (0, "Success"):
            self.state.log(f"Ubidots MQTT connect rc={rc}")
            return
        base = f"/v1.6/devices/{self.device_label}"
        client.subscribe(f"{base}/cmd_pause/lv", qos=1)
        client.subscribe(f"{base}/cmd_resume/lv", qos=1)
        # Cria/alinha as variaveis de comando no device (uma vez por conexao).
        self._sync_cmd_switches(force=True)
        self.publish_now()

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        topic = str(getattr(msg, "topic", "") or "").lower()
        value = _parse_lv(msg.payload)
        if value is None:
            return
        if topic.endswith("/cmd_pause/lv"):
            self.handle_command("cmd_pause", value)
        elif topic.endswith("/cmd_resume/lv"):
            self.handle_command("cmd_resume", value)
