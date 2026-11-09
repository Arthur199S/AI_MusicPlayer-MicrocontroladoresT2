"""Dashboard web FastAPI: metricas, controles e start/stop do motor."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .app_state import AppState
from .player import Player, PlayerError
from .voice_engine import VoiceEngine
from .youtube_search import YouTubeSearchError, find_audio_url

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _system_metrics() -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "cpu_percent": None,
        "ram_used_mb": None,
        "ram_total_mb": None,
        "ram_percent": None,
        "disk_used_gb": None,
        "disk_total_gb": None,
        "disk_percent": None,
        "temp_c": None,
    }
    try:
        import psutil
    except ImportError:
        return metrics

    metrics["cpu_percent"] = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    metrics["ram_used_mb"] = round(mem.used / (1024 ** 2), 1)
    metrics["ram_total_mb"] = round(mem.total / (1024 ** 2), 1)
    metrics["ram_percent"] = mem.percent
    disk = psutil.disk_usage("/")
    metrics["disk_used_gb"] = round(disk.used / (1024 ** 3), 2)
    metrics["disk_total_gb"] = round(disk.total / (1024 ** 3), 2)
    metrics["disk_percent"] = disk.percent

    thermal = Path("/sys/class/thermal/thermal_zone0/temp")
    if thermal.exists():
        try:
            raw = int(thermal.read_text().strip())
            metrics["temp_c"] = round(raw / 1000.0, 1)
        except (OSError, ValueError):
            pass
    return metrics


class PlayBody(BaseModel):
    query: str = Field(min_length=1)


def create_app(state: AppState, player: Player, engine: VoiceEngine) -> FastAPI:
    app = FastAPI(title="AI Music Player Dashboard", docs_url=None, redoc_url=None)
    expected_token = os.environ.get("DASHBOARD_TOKEN", "").strip()

    def require_auth(
        request: Request,
        authorization: str | None = Header(default=None),
        token: str | None = Query(default=None),
    ) -> None:
        if not expected_token:
            client = request.client.host if request.client else ""
            if client in ("127.0.0.1", "::1"):
                return
            raise HTTPException(
                status_code=401,
                detail="Defina DASHBOARD_TOKEN no .env para acesso remoto (ngrok).",
            )
        provided = token
        if not provided and authorization:
            parts = authorization.split(" ", 1)
            provided = parts[1].strip() if len(parts) == 2 else authorization.strip()
        if provided != expected_token:
            raise HTTPException(status_code=401, detail="Token invalido.")

    @app.get("/", response_class=HTMLResponse)
    def index(_: None = Depends(require_auth)) -> HTMLResponse:
        html_path = TEMPLATES_DIR / "dashboard.html"
        html = html_path.read_text(encoding="utf-8")
        # Injeta token no JS para as chamadas fetch (query string).
        safe_token = expected_token.replace("\\", "\\\\").replace('"', '\\"')
        html = html.replace("__DASHBOARD_TOKEN__", safe_token)
        return HTMLResponse(html)

    @app.get("/api/status")
    def status(_: None = Depends(require_auth)) -> JSONResponse:
        payload = state.snapshot()
        payload["system"] = _system_metrics()
        payload["engine_running"] = engine.running or payload["engine_running"]
        return JSONResponse(payload)

    @app.post("/api/pause")
    def pause(_: None = Depends(require_auth)) -> dict[str, str]:
        try:
            player.pause()
        except PlayerError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        state.clear_current_track(paused=True)
        state.log("Pause via dashboard.")
        return {"ok": "paused"}

    @app.post("/api/resume")
    def resume(_: None = Depends(require_auth)) -> dict[str, str]:
        try:
            player.resume()
        except PlayerError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        state.set_status("playing")
        state.log("Resume via dashboard.")
        return {"ok": "resumed"}

    @app.post("/api/stop")
    def stop_music(_: None = Depends(require_auth)) -> dict[str, str]:
        try:
            player.stop()
        except PlayerError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        state.clear_current_track(stopped=True)
        state.log("Stop via dashboard.")
        return {"ok": "stopped"}

    @app.post("/api/play")
    def play(body: PlayBody, _: None = Depends(require_auth)) -> dict[str, str]:
        query = body.query.strip()
        if not query:
            raise HTTPException(status_code=400, detail="query vazia")
        try:
            url = find_audio_url(query)
            player.play(url)
        except (PlayerError, YouTubeSearchError) as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        state.record_web_play()
        state.set_playing(query)
        state.log(f"Play via dashboard: {query}")
        return {"ok": "playing", "query": query}

    @app.post("/api/engine/start")
    def engine_start(_: None = Depends(require_auth)) -> dict[str, Any]:
        started = engine.start()
        return {"ok": True, "started": started, "running": engine.running}

    @app.post("/api/engine/stop")
    def engine_stop(_: None = Depends(require_auth)) -> dict[str, Any]:
        engine.stop(stop_audio=True)
        return {"ok": True, "running": engine.running}

    return app
