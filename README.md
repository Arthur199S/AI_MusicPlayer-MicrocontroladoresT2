# AI Music Player

Tocador de musica controlado por voz, executado em um Raspberry Pi 4. O sistema
reconhece uma wake word localmente, transcreve o comando com OpenAI
(`gpt-4o-mini-transcribe`), identifica a musica e a reproduz via YouTube.

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
- Busca com `yt-dlp` e reproducao com `mpv`

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
Busca da musica no YouTube (yt-dlp)
	|
	v
Reproducao do audio (mpv)
	|
	v
Alto-falante
```

Sem wake word o audio **nao** e enviado a API (economiza credito).

## Funcionalidades

- Capturar comandos de voz pelo microfone.
- Detectar wake word offline com Vosk.
- Transcrever o comando com OpenAI (portugues).
- Interpretar comandos para tocar, pausar, continuar, avancar e parar.
- Pesquisar musicas no YouTube.
- Reproduzir o audio no Raspberry Pi 4.
- Informar ao usuario quando o comando nao for compreendido ou quando houver
  falha de internet / API.

## Tecnologias

- **Python 3**: linguagem principal do projeto.
- **Vosk**: wake word local.
- **OpenAI Audio API**: STT do comando.
- **yt-dlp**: busca e obtencao do audio a partir do YouTube.
- **mpv**: reprodutor de audio via linha de comando.
- **Raspberry Pi OS**: sistema operacional do Raspberry Pi 4.

O uso do YouTube deve respeitar os termos de servico da plataforma, os direitos
autorais e a legislacao aplicavel.

## Requisitos

- Raspberry Pi 4 com Raspberry Pi OS.
- Python 3.10 ou mais recente.
- Microfone e saida de audio configurados.
- `mpv`, `ffmpeg` e `yt-dlp` disponiveis no `PATH`.
- Modelo portugues do Vosk (wake word).
- Conta OpenAI com credito prepaid e API key.
- Internet (YouTube + OpenAI).

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

Isso sobe o **dashboard** em `http://127.0.0.1:8080/` e, por padrao, o
motor de voz (`ENGINE_AUTOSTART=1`). Defina `DASHBOARD_TOKEN` no `.env`
(veja `.env.example`).

Fluxo de fala: diga a wake word e, em seguida, o comando. Exemplos:

- `assistente, toque evidencias`
- `assistente, pause`
- `assistente, pare`

### Dashboard web + ngrok

O painel mostra status, musica atual/ultima, frase reconhecida, requests,
linhas transcritas, tokens STT, CPU/RAM/disco, e permite Pause / Continuar /
Parar / Tocar + **Start/Stop** do motor de voz (sem derrubar o dashboard).

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

## Testes

Os testes unitarios (parser, OpenAI mock, buzzer mock) nao exigem microfone,
internet ou Raspberry Pi:

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

1. O programa inicia e aguarda a wake word no microfone (Vosk).
2. Apos a ativacao, grava um clip curto do comando.
3. A OpenAI transcreve o clip para texto em portugues.
4. O interpretador identifica a acao e o nome da musica.
5. O sistema pesquisa a musica no YouTube.
6. O `mpv` reproduz o audio encontrado.
7. O programa volta a aguardar a proxima wake word.

## Estrutura

```text
src/
  main.py                 # Dashboard + entry point
  voice_engine.py         # Loop de voz start/stop (thread)
  app_state.py            # Estado compartilhado (metricas)
  dashboard.py            # FastAPI + controles web
  templates/dashboard.html
  voice_recognition.py    # Wake word (Vosk) + gravacao do clip
  openai_transcribe.py    # Transcricao via OpenAI (+ usage)
  command_parser.py       # Interpretacao dos comandos
  youtube_search.py       # Busca da musica
  player.py               # Controle IPC do mpv
scripts/
  run_dashboard_tunnel.sh # ngrok -> dashboard
tests/
  ...
.env.example
requirements.txt
README.md
```

## Proximas etapas

1. Adicionar respostas faladas com Piper TTS.
2. Avaliar LLM local/nuvem para comandos mais naturais.
3. Criar testes de integracao com o player e tratar falhas de rede.
