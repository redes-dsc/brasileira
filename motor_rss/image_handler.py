"""
Shim para compatibilidade retroativa.
Redireciona chamadas para o Curador de Imagens Unificado.

⚠️ NÃO re-exporta upload_to_wordpress diretamente para evitar
   bypass da lógica de tiers e validação.
"""
import logging
import sys
from pathlib import Path

# Garante que o diretório raiz esteja no path para importar o curador
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from curador_imagens_unificado import (
    get_featured_image,
    search_unsplash,
    extract_image_from_content,
    is_valid_image_url,
)

logger = logging.getLogger("motor_rss")


def _is_valid_image_url(url: str) -> bool:
    """Wrapper compatível usando a validação do curador unificado."""
    return is_valid_image_url(url)
