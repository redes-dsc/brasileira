"""
Shim para compatibilidade retroativa.
Redireciona todas as chamadas para o novo Curador de Imagens Unificado.
"""
import logging
import sys
from pathlib import Path

# Garante que o diretório raiz esteja no path para importar o curador
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from curador_imagens_unificado import (
    get_featured_image,
    search_unsplash,
    upload_to_wordpress,
    extract_image_from_content
)

logger = logging.getLogger("motor_rss")

# As funções já estão importadas diretamente no topo, então o shim é automático e compatível.
def _is_valid_image_url(url: str) -> bool:
    from curador_imagens_unificado import get_curador
    return get_curador()._url_valida(url)
