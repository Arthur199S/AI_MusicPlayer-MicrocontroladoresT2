# AI Music Player

Tocador de musica controlado por voz, executado em um Raspberry Pi 4. O sistema
deve reconhecer o comando falado pelo usuario, identificar a musica solicitada e
reproduzi-la pela internet usando o YouTube.

## Objetivo

Permitir comandos como:

> Tocar Evidencias do Chitaozinho e Xororo

O projeto e desenvolvido em Python, com modulos independentes para facilitar
testes e futuras alteracoes.

## Estado atual

O MVP ja possui reconhecimento local com Vosk, interpretacao por regras em
Python, busca com `yt-dlp` e reproducao com `mpv`. O controle de pausa,
retomada, proxima musica e parada usa IPC do `mpv`. O Qwen pode ser adicionado
depois para entender frases mais livres, mas nao e necessario para os comandos
basicos.

## Arquitetura planejada

```text
Microfone
	|
	v
Reconhecimento de voz (Vosk)
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

## Funcionalidades

- Capturar comandos de voz pelo microfone.
- Converter a fala em texto usando reconhecimento de voz, preferencialmente
  offline.
- Interpretar comandos para tocar, pausar, continuar, avancar e parar.
- Pesquisar musicas no YouTube.
- Reproduzir o audio no Raspberry Pi 4.
- Informar ao usuario quando o comando nao for compreendido ou quando houver
  falha de internet.

## Tecnologias previstas

- **Python 3**: linguagem principal do projeto.
- **Vosk**: reconhecimento de voz local.
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
- Modelo de idioma portugues do Vosk.

## Instalacao no Raspberry Pi

```bash
sudo apt update
sudo apt install -y python3-venv mpv ffmpeg libportaudio2
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pip install --upgrade yt-dlp
```

Baixe um modelo portugues do Vosk e extraia-o em `models/`. O caminho pode ser
alterado pela variavel `VOSK_MODEL_PATH`.

## Execucao

```bash
source .venv/bin/activate
export VOSK_MODEL_PATH=models/vosk-model-small-pt-0.3
python -m src.main
```

Comandos de exemplo: `Tocar Evidencias`, `Pausar`, `Continuar`, `Proxima` e
`Parar`.

## Testes

Os testes do interpretador nao exigem microfone, internet ou Raspberry Pi:

```bash
python -m unittest discover -s tests -v
```

## Fluxo de funcionamento

1. O programa inicia e aguarda uma fala no microfone.
2. O mecanismo de reconhecimento converte a fala em texto.
3. O interpretador identifica a acao e o nome da musica.
4. O sistema pesquisa a musica no YouTube.
5. O `mpv` reproduz o audio encontrado.
6. O programa volta a aguardar o proximo comando.

## Sequencia de implementacao

1. Configurar o Raspberry Pi 4, o microfone e a saida de audio.
2. Criar um teste simples de captura e reconhecimento de voz.
3. Implementar o interpretador dos comandos em portugues.
4. Integrar a busca de musicas no YouTube.
5. Integrar o controle de reproducao com o `mpv`.
6. Tratar erros de reconhecimento, rede e musicas nao encontradas.
7. Testar o sistema completo e otimizar o desempenho no Raspberry Pi 4.

## Estrutura prevista

```text
src/
  main.py                 # Inicializacao e loop principal
  voice_recognition.py    # Captura e conversao da fala em texto
  command_parser.py       # Interpretacao dos comandos
  youtube_search.py       # Busca da musica
	player.py               # Controle IPC do mpv
tests/
	test_command_parser.py
requirements.txt
README.md

## Proximas etapas

1. Validar microfone e reconhecimento no Raspberry Pi.
2. Adicionar respostas faladas com Piper TTS.
3. Avaliar o Qwen 0.5B quantizado para comandos mais naturais.
4. Criar testes de integracao com o player e tratar falhas de rede.
```
