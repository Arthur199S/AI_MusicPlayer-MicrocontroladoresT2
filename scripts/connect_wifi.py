"""Wi-Fi bootstrap / conexao via NetworkManager (nmcli).

No boot (--bootstrap): tenta MAUA; se falhar, faz retry e cai para
Leonardo e Apto_163 (senhas no .env).

Uso:
  python -m scripts.connect_wifi --bootstrap
  python -m scripts.connect_wifi --bootstrap --dry-run
  python -m scripts.connect_wifi Leonardo
  python -m scripts.connect_wifi --status
  python -m scripts.connect_wifi --list
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Ordem padrao no bootstrap: campus primeiro, depois redes caseiras
DEFAULT_BOOTSTRAP_ORDER = ("MAUA", "Leonardo", "Apto_163")

# SSID -> variavel de ambiente com a senha (opcional para redes ja salvas no NM)
KNOWN_NETWORKS: dict[str, str] = {
    "MAUA": "WIFI_MAUA_PASSWORD",
    "Leonardo": "WIFI_LEONARDO_PASSWORD",
    "Apto_163": "WIFI_APTO_163_PASSWORD",
}

ALIASES: dict[str, str] = {
    "maua": "MAUA",
    "campus": "MAUA",
    "leonardo": "Leonardo",
    "casa": "Leonardo",
    "home": "Leonardo",
    "apto_163": "Apto_163",
    "apto163": "Apto_163",
    "apto": "Apto_163",
}

WLAN = "wlan0"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, text=True, capture_output=True)


def _ensure_nmcli() -> None:
    if not shutil.which("nmcli"):
        print(
            "nmcli nao encontrado. Instale NetworkManager:\n"
            "  sudo apt install -y network-manager",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _resolve_ssid(name: str) -> str:
    key = name.strip()
    if key in KNOWN_NETWORKS:
        return key
    return ALIASES.get(key.lower(), key)


def _password_for(ssid: str, override: str | None = None) -> str | None:
    if override:
        return override
    env_key = KNOWN_NETWORKS.get(ssid)
    if env_key:
        pwd = os.environ.get(env_key, "").strip()
        if pwd:
            return pwd
    pwd = os.environ.get("WIFI_PASSWORD", "").strip()
    return pwd or None


def _log(msg: str) -> None:
    print(msg, flush=True)


def current_ssid() -> str | None:
    r = _run(["nmcli", "-t", "-f", "GENERAL.CONNECTION", "device", "show", WLAN])
    if r.returncode != 0:
        return None
    name = (r.stdout or "").split(":", 1)[-1].strip()
    return name or None


def has_ipv4() -> bool:
    r = _run(["nmcli", "-t", "-f", "IP4.ADDRESS", "device", "show", WLAN])
    for line in (r.stdout or "").splitlines():
        if ":" in line and line.split(":", 1)[1].strip():
            return True
    return False


def is_online(timeout: float = 3.0) -> bool:
    """True se wlan0 tem IPv4 e consegue resolver/pingar um host publico."""
    if not has_ipv4():
        return False
    # ping -c1 -W timeout (segundos inteiros no iputils)
    wait = max(1, int(timeout))
    for host in ("1.1.1.1", "8.8.8.8"):
        r = _run(["ping", "-c", "1", "-W", str(wait), host])
        if r.returncode == 0:
            return True
    return False


def wifi_rescan() -> None:
    _run(["nmcli", "device", "wifi", "rescan"])
    time.sleep(2)


def visible_ssids() -> set[str]:
    r = _run(["nmcli", "-t", "-f", "SSID", "device", "wifi", "list"])
    found: set[str] = set()
    for line in (r.stdout or "").splitlines():
        ssid = line.strip()
        if ssid:
            found.add(ssid)
    return found


def _profile_exists(ssid: str) -> bool:
    r = _run(["nmcli", "-t", "-f", "NAME", "connection", "show"])
    names = {(line or "").strip() for line in (r.stdout or "").splitlines()}
    return ssid in names


def connect(ssid: str, password: str | None = None, *, timeout: int = 30) -> bool:
    """Tenta associar wlan0 ao SSID. Retorna True se ficou com IPv4."""
    _ensure_nmcli()
    ssid = _resolve_ssid(ssid)
    password = password if password is not None else _password_for(ssid)

    _log(f"-> tentando '{ssid}'...")

    # Perfil ja salvo no NetworkManager (ex.: MAUA no campus)
    if _profile_exists(ssid) and not password:
        r = _run(["nmcli", "connection", "up", ssid])
    elif password:
        r = _run(
            [
                "nmcli",
                "device",
                "wifi",
                "connect",
                ssid,
                "password",
                password,
                "ifname",
                WLAN,
            ]
        )
    elif _profile_exists(ssid):
        r = _run(["nmcli", "connection", "up", ssid])
    else:
        # Rede aberta ou sem senha configurada
        r = _run(["nmcli", "device", "wifi", "connect", ssid, "ifname", WLAN])

    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode != 0:
        _log(f"   falhou ({r.returncode}): {out or 'sem detalhe'}")
        return False

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if current_ssid() and has_ipv4():
            _log(f"   ok: {WLAN} -> {current_ssid()} (IPv4)")
            return True
        time.sleep(1)

    _log(f"   associado mas sem IPv4 a tempo ({timeout}s)")
    return False


def bootstrap_order() -> list[str]:
    raw = os.environ.get("WIFI_BOOTSTRAP_ORDER", "").strip()
    if raw:
        return [_resolve_ssid(p) for p in raw.split(",") if p.strip()]
    return list(DEFAULT_BOOTSTRAP_ORDER)


def bootstrap(
    *,
    retries: int | None = None,
    delay: float | None = None,
    connect_timeout: int = 30,
    dry_run: bool = False,
) -> int:
    """Retry no boot: MAUA primeiro; se nao der, Leonardo / Apto_163."""
    _ensure_nmcli()
    retries = retries if retries is not None else int(
        os.environ.get("WIFI_BOOTSTRAP_RETRIES", "5")
    )
    delay = delay if delay is not None else float(
        os.environ.get("WIFI_BOOTSTRAP_DELAY", "8")
    )
    order = bootstrap_order()

    _log(f"Wi-Fi bootstrap: ordem={order} retries={retries} delay={delay}s")

    # Campus (MAUA) muitas vezes bloqueia ICMP: IPv4 no wlan0 ja basta.
    active = current_ssid()
    if active and has_ipv4():
        ping_ok = is_online()
        _log(
            f"Ja conectado em '{active}' com IPv4"
            f" (ping={'ok' if ping_ok else 'falhou/bloqueado'}) — nada a fazer."
        )
        return 0

    for attempt in range(1, retries + 1):
        _log(f"\n=== tentativa {attempt}/{retries} ===")
        wifi_rescan()
        visible = visible_ssids()
        _log(f"Visiveis: {', '.join(sorted(visible)) or '(nenhuma)'}")

        planned = 0
        for ssid in order:
            if visible and ssid not in visible:
                _log(f"-> '{ssid}' fora de alcance, pulando")
                continue

            if dry_run:
                pwd = _password_for(ssid)
                has_profile = _profile_exists(ssid)
                _log(
                    f"-> [dry-run] conectaria '{ssid}' "
                    f"(perfil={'sim' if has_profile else 'nao'}, "
                    f"senha={'sim' if pwd else 'nao'})"
                )
                planned += 1
                continue

            if connect(ssid, timeout=connect_timeout):
                time.sleep(2)
                if has_ipv4():
                    _log(f"Bootstrap OK em '{ssid}'")
                    return 0
                _log(f"'{ssid}' sem IPv4 util, tentando proxima...")

        if dry_run:
            _log(f"Dry-run concluido ({planned} rede(s) no plano).")
            return 0

        if attempt < retries:
            _log(f"Aguardando {delay}s antes do proximo ciclo...")
            time.sleep(delay)

    _log("Bootstrap falhou: nenhuma rede da lista respondeu.")
    return 1


def status() -> int:
    _ensure_nmcli()
    r = _run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"])
    print("Dispositivos:")
    for line in (r.stdout or "").strip().splitlines():
        parts = line.split(":")
        if len(parts) >= 4 and parts[1] == "wifi":
            print(f"  {parts[0]}: {parts[2]} -> {parts[3] or '(nenhuma)'}")
    online = is_online()
    print(f"Online (ping): {'sim' if online else 'nao'}")
    r2 = _run(
        ["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL,SECURITY", "device", "wifi", "list"]
    )
    print("\nRedes visiveis:")
    seen: set[str] = set()
    for line in (r2.stdout or "").strip().splitlines():
        parts = line.split(":")
        if len(parts) < 4:
            continue
        active, ssid, signal, security = parts[0], parts[1], parts[2], parts[3]
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        mark = "*" if active == "yes" else " "
        print(f"  {mark} {ssid:32} sinal={signal:>3}%  {security}")
    return 0


def list_known() -> int:
    print("Redes conhecidas:")
    for ssid, env_key in KNOWN_NETWORKS.items():
        configured = "ok" if os.environ.get(env_key, "").strip() else "sem senha no .env"
        profile = "perfil NM" if _profile_exists(ssid) else "sem perfil"
        print(f"  {ssid:16} ({env_key}: {configured}; {profile})")
    print(f"\nOrdem bootstrap: {', '.join(bootstrap_order())}")
    return 0


def main() -> int:
    load_dotenv(_repo_root() / ".env")

    parser = argparse.ArgumentParser(
        description="Wi-Fi: conexao manual ou bootstrap com fallback (MAUA -> casa)"
    )
    parser.add_argument(
        "ssid",
        nargs="?",
        default=None,
        help="SSID ou apelido (MAUA, Leonardo, Apto_163). Ignorado com --bootstrap",
    )
    parser.add_argument("--password", "-p", default=None, help="Senha (sobrescreve .env)")
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Modo boot: tenta MAUA e faz fallback/retry para Leonardo/Apto_163",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Com --bootstrap, so mostra o plano (nao conecta)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=None,
        help="Ciclos de retry no bootstrap (padrao: WIFI_BOOTSTRAP_RETRIES ou 5)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Segundos entre ciclos (padrao: WIFI_BOOTSTRAP_DELAY ou 8)",
    )
    parser.add_argument("--list", action="store_true", help="Lista redes predefinidas")
    parser.add_argument("--status", action="store_true", help="Mostra Wi-Fi atual e scan")
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout por rede aguardando IPv4 (padrao 30)",
    )
    args = parser.parse_args()

    if args.list:
        return list_known()
    if args.status:
        return status()
    if args.bootstrap:
        return bootstrap(
            retries=args.retries,
            delay=args.delay,
            connect_timeout=args.timeout,
            dry_run=args.dry_run,
        )

    raw = args.ssid or os.environ.get("WIFI_SSID", "Leonardo").strip() or "Leonardo"
    ssid = _resolve_ssid(raw)
    ok = connect(ssid, args.password, timeout=args.timeout)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
