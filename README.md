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

Fluxo de fala: diga a wake word e, em seguida, o comando. Exemplos:

- `assistente, toque evidencias`
- `jarvis, pause`
- `assistente, pare`

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
  main.py                 # Inicializacao e loop principal
  voice_recognition.py    # Wake word (Vosk) + gravacao do clip
  openai_transcribe.py    # Transcricao via OpenAI
  command_parser.py       # Interpretacao dos comandos
  youtube_search.py       # Busca da musica
  player.py               # Controle IPC do mpv
tests/
  test_command_parser.py
  test_openai_transcribe.py
.env.example
requirements.txt
README.md
```

## Proximas etapas

1. Adicionar respostas faladas com Piper TTS.
2. Avaliar LLM local/nuvem para comandos mais naturais.
3. Criar testes de integracao com o player e tratar falhas de rede.
