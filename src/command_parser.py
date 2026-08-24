"""Interpretacao deterministica dos comandos de voz."""

import re
import unicodedata


_ACTION_WORDS = {
    "pausar": ("pausar", "pause"),
    "continuar": ("continuar", "retomar", "proseguir"),
    "parar": ("parar", "pare", "stop"),
    "proxima": ("proxima", "seguinte"),
}


def normalize(text: str) -> str:
    """Remove acentos e normaliza o texto para comparacao."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )


def parse_command(text: str) -> dict[str, str]:
    """Converte uma frase reconhecida em uma acao e seus dados."""
    normalized = normalize(text).strip()

    for action, words in _ACTION_WORDS.items():
        if any(re.search(rf"\b{re.escape(word)}\b", normalized) for word in words):
            return {"action": action}

    match = re.search(r"\b(?:tocar|reproduzir|ouvir)\b\s+(.+)", normalized)
    if match:
        return {"action": "tocar", "query": match.group(1).strip()}

    return {"action": "desconhecido"}
