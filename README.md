# AI Music Player

Tocador de musica controlado por voz, executado em um Raspberry Pi 4. O sistema
reconhece uma wake word localmente, transcreve o comando com OpenAI
(`gpt-4o-mini-transcribe`), identifica a musica e a reproduz via YouTube.

Ha tambem um **dashboard local** (FastAPI) com as mesmas metricas de um painel
IoT (now playing, contador do dia, gauges, latencia, switch de pause) e uma
ponte MQTT opcional para **Ubidots STEM**.

## Objetivo

Permitir comandos como:

> Assistente, tocar Evidencias do Chitaozinho e Xororo

O projeto e desenvolvido em Python, com modulos independentes para facilitar
testes e futuras alteracoes.

## Estado atual

O MVP usa:

- **Vosk** (local) so para detectar a wake word (`assistente` / `jarvis` e variantes)
- **OpenAI** `gpt-4o-mini-transcribe` para converter o comando em texto
- Interpretacao por regras em Python
- Busca com `yt-dlp` (URL + **titulo real** do YouTube) e reproducao com `mpv`
- Dashboard web local com telemetria e controles
- Bridge MQTT opcional para Ubidots STEM (telemetria + Pause/Continuar)

## Arquitetura

```text
Microfone
	|
	v
Wake word local (Vosk)
	|
	v
Grava clip do comando
	|
	v
Transcricao OpenAI (gpt-4o-mini-transcribe)
	|
	v
Interpretacao do comando
	|
	v
Busca no YouTube (yt-dlp -> URL + titulo)
	|
	v
Reproducao (mpv) -----> Alto-falante
	|
	+--> AppState (metricas) --> Dashboard local (/)
	                         \-> Ubidots MQTT (opcional)
```

Sem wake word o audio **nao** e enviado a API (economiza credito).

## Funcionalidades

### Voz e reproducao

- Capturar comandos de voz pelo microfone.
- Detectar wake word offline com Vosk.
- Transcrever o comando com OpenAI (portugues).
- Interpretar comandos para tocar, pausar, continuar, avancar e parar.
- Buscar musicas no YouTube e gravar o **titulo real** da faixa (nao o comando falado).
- Reproduzir o audio no Raspberry Pi 4 via `mpv` (IPC: pause idempotente, progresso).
- Feedback sonoro no alto-falante (bip apos wake word).

### Dashboard local (`http://127.0.0.1:8080/`)

Demo visual das metricas (atualiza a cada 2 s), sem depender de nuvem:

- Status do aparelho / motor de voz
- **Musica tocando** (titulo YouTube) ou `nada tocando`
- **Quantas musicas tocou hoje** (`tracks_today`, reset diario)
- Segundos restantes da faixa (`mpv` time-pos / duration)
- **Historico das ultimas 5 musicas**
- Gauges de temperatura, CPU e RAM
- Latencia STT (ms) e latencia ponta a ponta wake → acao (ms)
- Switch de **Pause** (fica ligado enquanto pausado)
- Controles: Start/Stop do motor, Parar, Tocar por texto
- Frase reconhecida e log recente

Acesso: `http://127.0.0.1:8080/?token=SEU_DASHBOARD_TOKEN`

### Ubidots STEM (MQTT, opcional)

O Pi pode publicar telemetria e receber **Pause / Continuar** via MQTT.

Variaveis publicadas:

| Variavel | Conteudo |
|----------|----------|
| `app_status` | Codigo: 0 parado … 4 tocando … 5 pausado … 6 erro |
| `now_playing` | `value` 0/1 + `context.track` = titulo (ou `nada tocando`) |
| `tracks_today` | Musicas iniciadas hoje |
| `seconds_left` | Segundos restantes |
| `cpu_percent` / `temp_c` / `ram_percent` | Saude do Pi |
| `engine_running` / `heartbeat` | Motor e “online” |
| `stt_latency_ms` / `e2e_latency_ms` | Tempo de resposta |
| `cmd_pause` / `cmd_resume` | Downlink (switch/botao) |

**Cota de dots:** cada valor publicado = 1 dot. Se a conta estourar
(`User dots limit reached`), o MQTT continua “conectado” mas o Ubidots
**descarta** os dados. Por isso:

- Eventos (`now_playing`, `app_status`, `tracks_today`, latencias, …) so sobem **quando mudam**
- Saude (`cpu` / `temp` / `ram` / `heartbeat` / `seconds_left`) sobe a cada
  `UBIDOTS_PUBLISH_INTERVAL` (padrao **300 s**, minimo 30)
- `cmd_pause` nao vai no publish periodico (evita loop de eco pause/resume)

Debug do que o Pi envia vs o que o Ubidots recebeu:

`http://127.0.0.1:8080/live?token=SEU_DASHBOARD_TOKEN`

Sem `UBIDOTS_TOKEN` o app sobe normalmente e pula o MQTT. O dashboard local
continua funcionando 100%.

## Tecnologias

- **Python 3** + **FastAPI** / **uvicorn** (dashboard)
- **Vosk**: wake word local
- **OpenAI Audio API**: STT do comando
- **yt-dlp**: busca YouTube (URL + titulo)
- **mpv**: reprodutor via IPC Unix socket
- **paho-mqtt**: ponte Ubidots (opcional)
- **psutil**: metricas de sistema
- **Raspberry Pi OS**

O uso do YouTube deve respeitar os termos de servico da plataforma, os direitos
autorais e a legislacao aplicavel.

## Requisitos

- Raspberry Pi 4 com Raspberry Pi OS.
- Python 3.10 ou mais recente.
- Microfone e saida de audio configurados.
- `mpv`, `ffmpeg` e `yt-dlp` disponiveis no `PATH`.
- Modelo portugues do Vosk (wake word).
- Conta OpenAI com credito prepaid e API key.
- Internet (YouTube + OpenAI; Ubidots so se usar MQTT).

## Instalacao no Raspberry Pi

```bash
sudo apt update
sudo apt install -y python3-venv mpv ffmpeg libportaudio2 python3-lgpio
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pip install --upgrade yt-dlp
```

Baixe um modelo portugues do Vosk e extraia-o em `models/` (ou use
`python baixar.py`). O caminho pode ser alterado por `VOSK_MODEL_PATH`.

### OpenAI (obrigatorio)

1. Crie conta em https://platform.openai.com
2. Ative billing prepaid (minimo tipico US$ 5; US$ 10 cobre meses de uso domestico)
3. Desligue auto-recharge no inicio, se quiser controlar gastos
4. Crie uma API key (`sk-...`)
5. Copie o template e preencha a chave:

```bash
cp .env.example .env
# edite .env e coloque OPENAI_API_KEY=sk-...
# e DASHBOARD_TOKEN=um-segredo-forte
```

O arquivo `.env` ja esta no `.gitignore` — nao commite a chave.

Custo aproximado com `gpt-4o-mini-transcribe`: cerca de US$ 0,003 por minuto de
audio enviado. Comandos curtos (~5 s) e dezenas por dia ficam na casa dos
centavos por mes.

## Execucao

```bash
source .venv/bin/activate
export VOSK_MODEL_PATH=models/vosk-model-small-pt-0.3
python -m src.main
```

Isso sobe:

1. Dashboard em `http://127.0.0.1:8080/`
2. Motor de voz (se `ENGINE_AUTOSTART=1`, padrao)
3. Bridge Ubidots MQTT (se `UBIDOTS_TOKEN` estiver no `.env`)

Fluxo de fala: diga a wake word e, em seguida, o comando. Exemplos:

- `assistente, toque evidencias`
- `assistente, pause`
- `assistente, continue`
- `assistente, pare`

### Acesso remoto (ngrok)

```bash
# no .env:
# DASHBOARD_TOKEN=um-segredo-forte
# DASHBOARD_PORT=8080

python -m src.main
# outro terminal:
chmod +x scripts/run_dashboard_tunnel.sh
./scripts/run_dashboard_tunnel.sh
```

Abra a URL `https://...ngrok...` e use `?token=SEU_DASHBOARD_TOKEN`.
Instale o ngrok e configure: `ngrok config add-authtoken ...`.

## Configurar Ubidots (opcional)

1. Conta STEM → **API Credentials** → copie o **Token**.
2. Crie um device com label igual a `UBIDOTS_DEVICE_LABEL` (ex. `ai-music-player-microcontrolar`).
3. No `.env`:

```bash
UBIDOTS_TOKEN=seu-token
UBIDOTS_DEVICE_LABEL=ai-music-player-microcontrolar
# UBIDOTS_PUBLISH_INTERVAL=300
```

4. Reinicie o app. As variaveis aparecem no device apos o primeiro publish.
5. No dashboard STEM:
   - Metric / Indicator: `app_status`, `now_playing` (**mostrar context `track`**), `tracks_today`
   - Gauges: `cpu_percent`, `temp_c`, `ram_percent`, latencias
   - Switch: `cmd_pause` (1 = pausado, 0 = tocando). O Pi mantem o valor alinhado ao estado.
   - Botao opcional: `cmd_resume` (envia 1; o Pi zera depois)

Broker: `industrial.api.ubidots.com:1883` (username = token, password vazio).

Se a pagina `/live` mostrar “MQTT conectado” mas “Ultimo update” parado ha
minutos, quase sempre e **cota de dots** — confira Usage na conta Ubidots.

## Testes

Os testes unitarios (parser, OpenAI mock, buzzer, app_state, ubidots, youtube)
nao exigem microfone, internet ou Raspberry Pi:

```bash
python -m unittest discover -s tests -v
```

### Teste do microfone

```bash
python -m scripts.test_mic
python -m scripts.test_mic --stereo --seconds 15
python -m scripts.test_mic --vosk --seconds 20
```

### Teste do bip de feedback

O app usa o **alto-falante do Voice HAT** (mesmo caminho do `speaker-test`),
nao o piezo no GPIO. O scan `--gpio` so mexe em Drivers; se nao ha piezo
ligado, fica silencioso — isso e esperado.

```bash
python -m scripts.test_buzzer              # bip no alto-falante (padrao)
python -m scripts.test_buzzer --count 2
python -m scripts.test_buzzer --gpio       # piezo GPIO (se existir hardware)
python -m scripts.test_buzzer --gpio --scan
```

Volume / device do bip (mesmo caminho do `speaker-test -D plughw:3,0`):

```bash
amixer -c 3 sset PCM 90% unmute
python -m scripts.test_buzzer              # escolhe Headphones automaticamente
python -m scripts.test_buzzer --device 1   # forca PortAudio index 1
```

## Fluxo de funcionamento

1. O programa inicia o dashboard (+ MQTT se configurado) e aguarda a wake word.
2. Apos a ativacao, grava um clip curto do comando e mede latencia.
3. A OpenAI transcreve o clip; o estado guarda `stt_latency_ms`.
4. O interpretador identifica a acao e o nome da musica.
5. O sistema pesquisa a musica no YouTube e obtém URL + titulo.
6. O `mpv` reproduz; `AppState` atualiza now playing, `tracks_today` e historico.
7. Dashboard / Ubidots refletem as metricas; Pause remoto ou local controla o mpv.
8. O programa volta a aguardar a proxima wake word (sem apagar status de musica).

## Estrutura

```text
src/
  main.py                 # Dashboard + voice + Ubidots entry point
  voice_engine.py         # Loop de voz start/stop (thread)
  app_state.py            # Estado compartilhado (metricas, historico, latencias)
  dashboard.py            # FastAPI: / , /live , /api/*
  ubidots_mqtt.py         # Telemetria + Pause/Continuar via MQTT
  system_metrics.py       # CPU/RAM/disco/temp
  templates/
    dashboard.html        # Demo local (painel principal)
    live.html             # Debug Pi vs Ubidots
  voice_recognition.py    # Wake word (Vosk) + gravacao do clip
  openai_transcribe.py    # Transcricao via OpenAI (+ usage + latency_ms)
  command_parser.py       # Interpretacao dos comandos
  youtube_search.py       # Busca: AudioResult(url, title, query)
  player.py               # Controle IPC do mpv (+ playback_snapshot)
  speaker_beep.py         # Bip no alto-falante
  buzzer.py               # Piezo GPIO (opcional)
scripts/
  run_dashboard_tunnel.sh # ngrok -> dashboard
  test_mic.py / test_buzzer.py / connect_wifi.py
tests/
  test_app_state.py
  test_ubidots_mqtt.py
  test_youtube_search.py
  ...
.env.example
requirements.txt
README.md
```

## Variaveis de ambiente relevantes

Veja `.env.example` completo. Principais:

| Variavel | Uso |
|----------|-----|
| `OPENAI_API_KEY` | Obrigatorio — STT |
| `DASHBOARD_TOKEN` | Auth do dashboard (obrigatorio fora de localhost) |
| `DASHBOARD_HOST` / `DASHBOARD_PORT` | Bind do FastAPI (padrao 127.0.0.1:8080) |
| `ENGINE_AUTOSTART` | `1` sobe o motor de voz junto (padrao) |
| `UBIDOTS_TOKEN` | Se vazio, MQTT desligado |
| `UBIDOTS_DEVICE_LABEL` | Label do device no Ubidots |
| `UBIDOTS_PUBLISH_INTERVAL` | Intervalo da telemetria de saude (padrao 300 s) |
| `MPV_AUDIO_DEVICE` | Saida ALSA do mpv |
| `VOSK_MODEL_PATH` | Modelo da wake word |

## Proximas etapas

1. Adicionar respostas faladas com Piper TTS.
2. Avaliar LLM local/nuvem para comandos mais naturais.
3. Criar testes de integracao com o player e tratar falhas de rede.
