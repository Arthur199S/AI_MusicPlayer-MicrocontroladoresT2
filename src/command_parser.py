"""Interpretacao deterministica dos comandos de voz."""

import re
import unicodedata


# "jarvis" costuma sair errado no Vosk PT; incluir variantes comuns.
# No modelo small-pt so "assistente" e "jarbas" existem no vocabulario.
WAKE_WORDS = (
    "jarvis",
    "jarves",
    "jarbas",
    "assistente",
    "assistencia",
    "assistent",
)

_ACTION_WORDS = {
    "pausar": ("pausar", "pause", "pausa"),
    "continuar": ("continuar", "retomar", "proseguir"),
    "parar": ("parar", "pare", "stop"),
    "proxima": ("proxima", "proximo", "seguinte"),
}

_PLAY_WORDS = ("tocar", "toque", "toca", "reproduzir", "ouvir")


def normalize(text: str) -> str:
    """Remove acentos e normaliza o texto para comparacao."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )


def _strip_wake_word(normalized: str) -> tuple[str, bool]:
    """Remove o prefixo de ativacao, se houver.

    Retorna (comando, usou_wake_word).
    """
    for wake in WAKE_WORDS:
        match = re.match(rf"^{re.escape(wake)}\b[,:]?\s*(.*)$", normalized)
        if match:
            return match.group(1).strip(), True
    return normalized, False


def contains_wake_word(text: str) -> bool:
    """True se o texto normalizado contem alguma wake word."""
    normalized = normalize(text)
    return any(
        re.search(rf"\b{re.escape(wake)}\b", normalized) for wake in WAKE_WORDS
    )


def parse_command(text: str) -> dict[str, str]:
    """Converte uma frase reconhecida em uma acao e seus dados.

    A wake word e opcional: ajuda a filtrar, mas o comando tambem
    funciona sem ela (ex.: "toque evidencias").
    """
    normalized = normalize(text).strip()
    command, used_wake = _strip_wake_word(normalized)

    if used_wake and not command:
        return {"action": "aguardar"}

    for action, words in _ACTION_WORDS.items():
        if any(re.search(rf"\b{re.escape(word)}\b", command) for word in words):
            return {"action": action}

    play_pattern = r"\b(?:%s)\b\s+(.+)" % "|".join(_PLAY_WORDS)
    match = re.search(play_pattern, command)
    if match:
        query = match.group(1).strip()
        query = re.sub(r"^(?:uma|a|o)?\s*musica\s+", "", query).strip()
        if query:
            return {"action": "tocar", "query": query}

    return {"action": "desconhecido"}
