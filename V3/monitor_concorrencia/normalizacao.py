"""Normalização de texto em português."""

from __future__ import annotations

import re
import unicodedata

STOPWORDS_PT = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "para", "por", "com", "um", "uma",
    "na", "no", "nas", "nos", "ao", "aos", "que", "se", "como", "mais", "menos", "sobre",
}


def normalize_portuguese(text: str) -> list[str]:
    """Normaliza texto e remove stopwords básicas."""

    ascii_text = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(ch for ch in ascii_text if not unicodedata.combining(ch))
    ascii_text = re.sub(r"[^a-z0-9\s]", " ", ascii_text)
    tokens = [token for token in ascii_text.split() if token and token not in STOPWORDS_PT]
    return tokens
