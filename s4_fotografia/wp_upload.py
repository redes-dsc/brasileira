"""
Upload de Imagens WordPress — Sistema 4 Fotografia
brasileira.news · V2

Funções para download, processamento e upload de imagens:
- download_image: baixa imagem de URL externa
- smart_crop: recorta imagem para 16:9 (1200x675)
- upload_image_to_wordpress: faz upload via REST API
- process_and_upload: pipeline completo
"""

import io
import sys
import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple

import requests

# Adiciona o diretório do projeto ao path para imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json as _json

def _safe_json(resp):
    """Parse JSON tratando BOM UTF-8."""
    return _json.loads(resp.text.lstrip("\ufeff"))

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuração
# ─────────────────────────────────────────────────────────────────────────────

# Dimensões padrão para featured image (tema Newspaper)
TARGET_WIDTH = 1200
TARGET_HEIGHT = 675  # Ratio 16:9

# Timeout para download de imagens
DOWNLOAD_TIMEOUT = 30
UPLOAD_TIMEOUT = 60

# Content types aceitos
VALID_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}

# Importa configurações do motor_rss
import os

# Import shared WP session for connection pooling
from s4_fotografia.wp_api import get_wp_session

try:
    from motor_rss import config as wp_config

    WP_API_BASE = wp_config.WP_API_BASE
except ImportError:
    WP_URL = os.environ.get("WP_URL", "https://brasileira.news")
    WP_API_BASE = f"{WP_URL}/wp-json/wp/v2"


# ─────────────────────────────────────────────────────────────────────────────
# Download de Imagem
# ─────────────────────────────────────────────────────────────────────────────


def download_image(
    url: str,
    timeout: int = DOWNLOAD_TIMEOUT,
) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Faz download de uma imagem de URL externa.

    Valida o content-type da resposta para garantir que é uma imagem.

    Args:
        url: URL da imagem a baixar
        timeout: Timeout em segundos

    Returns:
        Tuple (image_bytes, content_type) ou (None, None) se falhar
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "image/jpeg,image/png,image/webp,image/gif,image/*",
            "Referer": url.split("/")[0] + "//" + url.split("/")[2] + "/",
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            stream=True,
        )
        response.raise_for_status()

        # Valida content-type
        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        if content_type not in VALID_CONTENT_TYPES:
            logger.warning(f"Content-type inválido para {url}: {content_type}")
            return None, None

        # Lê conteúdo
        image_bytes = response.content
        if not image_bytes:
            logger.warning(f"Imagem vazia em {url}")
            return None, None

        logger.debug(f"Download concluído: {url} ({len(image_bytes)} bytes)")
        return image_bytes, content_type

    except requests.RequestException as e:
        logger.error(f"Erro ao baixar imagem {url}: {e}")
        return None, None
    except Exception as e:
        logger.error(f"Erro inesperado ao baixar {url}: {e}")
        return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Smart Crop (16:9)
# ─────────────────────────────────────────────────────────────────────────────


def smart_crop(
    image_bytes: bytes,
    target_width: int = TARGET_WIDTH,
    target_height: int = TARGET_HEIGHT,
) -> bytes:
    """
    Redimensiona e recorta imagem para o tamanho alvo com crop centralizado.

    Preserva proporção da imagem original, aplicando crop center-weighted
    para manter o enquadramento mais relevante.

    Args:
        image_bytes: Bytes da imagem original
        target_width: Largura alvo em pixels
        target_height: Altura alvo em pixels

    Returns:
        Bytes da imagem processada (JPEG quality 85)
    """
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))

        # Converte para RGB (remove alpha channel se houver)
        if img.mode in ("RGBA", "LA", "P"):
            # Cria background branco para transparência
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        orig_w, orig_h = img.size
        target_ratio = target_width / target_height
        orig_ratio = orig_w / orig_h

        if orig_ratio > target_ratio:
            # Imagem mais larga que o alvo → recorta nas laterais
            new_h = orig_h
            new_w = int(orig_h * target_ratio)
            left = (orig_w - new_w) // 2
            img = img.crop((left, 0, left + new_w, orig_h))
        else:
            # Imagem mais alta que o alvo → recorta em cima/baixo
            # Mantém mais do topo (rostos geralmente estão no topo)
            new_w = orig_w
            new_h = int(orig_w / target_ratio)
            # Crop com bias para o topo (30% do topo, 70% do resto)
            top = int((orig_h - new_h) * 0.3)
            img = img.crop((0, top, orig_w, top + new_h))

        # Redimensiona para tamanho final
        img = img.resize((target_width, target_height), Image.LANCZOS)

        # Salva como JPEG com qualidade 85
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=85, optimize=True)
        return output.getvalue()

    except ImportError:
        logger.error("Pillow não instalado. Execute: pip install Pillow")
        return image_bytes
    except Exception as e:
        logger.warning(f"Erro no smart_crop, retornando original: {e}")
        return image_bytes


# ─────────────────────────────────────────────────────────────────────────────
# Upload para WordPress
# ─────────────────────────────────────────────────────────────────────────────


def upload_image_to_wordpress(
    image_bytes: bytes,
    filename: str,
    caption: str = "",
    alt_text: str = "",
    description: str = "",
) -> Optional[int]:
    """
    Faz upload de imagem para WordPress via REST API.

    Args:
        image_bytes: Bytes da imagem já processada
        filename: Nome do arquivo (ex: "s4-abc123.jpg")
        caption: Legenda da imagem
        alt_text: Texto alternativo para acessibilidade
        description: Descrição da imagem

    Returns:
        media_id do WordPress ou None se falhar
    """
    try:
        url = f"{WP_API_BASE}/media"

        # Determina content-type pelo filename
        if filename.lower().endswith(".png"):
            content_type = "image/png"
        elif filename.lower().endswith(".webp"):
            content_type = "image/webp"
        elif filename.lower().endswith(".gif"):
            content_type = "image/gif"
        else:
            content_type = "image/jpeg"

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": content_type,
        }

        session = get_wp_session()
        response = session.post(
            url,
            data=image_bytes,
            headers=headers,
            timeout=UPLOAD_TIMEOUT,
        )
        response.raise_for_status()

        media = _safe_json(response)
        media_id = media.get("id")

        if not media_id:
            logger.error(f"Upload retornou sem ID: {response.text[:200]}")
            return None

        logger.info(f"Imagem uploaded: {filename} → media_id={media_id}")

        # Atualiza metadados (caption, alt, description)
        if caption or alt_text or description:
            _update_media_metadata(media_id, caption, alt_text, description)

        return media_id

    except requests.RequestException as e:
        logger.error(f"Erro no upload da imagem: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado no upload: {e}")
        return None


def _update_media_metadata(
    media_id: int,
    caption: str,
    alt_text: str,
    description: str,
) -> bool:
    """
    Atualiza metadados de uma mídia já carregada.

    Args:
        media_id: ID da mídia no WordPress
        caption: Legenda
        alt_text: Texto alternativo
        description: Descrição

    Returns:
        True se atualizado com sucesso
    """
    try:
        url = f"{WP_API_BASE}/media/{media_id}"
        data = {}

        if caption:
            data["caption"] = caption
        if alt_text:
            data["alt_text"] = alt_text
        if description:
            data["description"] = description

        if not data:
            return True

        session = get_wp_session()
        response = session.post(
            url,
            json=data,
            timeout=30,
        )
        response.raise_for_status()
        return True

    except Exception as e:
        logger.warning(f"Erro ao atualizar metadados da mídia {media_id}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Completo
# ─────────────────────────────────────────────────────────────────────────────


def process_and_upload(
    image_url: str,
    caption_text: str,
    author: str,
    license_type: str,
    alt_text: str = "",
) -> Optional[int]:
    """
    Pipeline completo: download → crop → upload → retorna media_id.

    Gera filename único baseado em hash da URL original.
    Formata caption com créditos.

    Args:
        image_url: URL da imagem original
        caption_text: Descrição/legenda da imagem
        author: Autor/fotógrafo
        license_type: Tipo de licença (CC BY, domínio público, etc.)
        alt_text: Texto alternativo (usa caption se vazio)

    Returns:
        media_id do WordPress ou None se falhar
    """
    try:
        # 1. Download
        image_bytes, content_type = download_image(image_url)
        if not image_bytes:
            logger.error(f"Falha no download de {image_url}")
            return None

        # 2. Crop para 16:9
        processed_bytes = smart_crop(image_bytes)

        # 3. Gera filename único
        url_hash = hashlib.md5(image_url.encode()).hexdigest()[:12]
        filename = f"s4-{url_hash}.jpg"

        # 4. Formata caption com créditos
        caption = caption_text.strip() if caption_text else ""
        if author:
            credit_line = f"Foto: {author}"
            if license_type:
                credit_line += f" — {license_type}"
            if caption:
                caption = f"{caption}\n\n{credit_line}"
            else:
                caption = credit_line

        # 5. Alt text padrão
        if not alt_text:
            alt_text = caption_text[:125] if caption_text else ""

        # 6. Description com informações completas
        description = f"Imagem: {image_url}\nFonte: {author}\nLicença: {license_type}"

        # 7. Upload
        media_id = upload_image_to_wordpress(
            image_bytes=processed_bytes,
            filename=filename,
            caption=caption,
            alt_text=alt_text,
            description=description,
        )

        return media_id

    except Exception as e:
        logger.error(f"Erro no process_and_upload para {image_url}: {e}")
        return None

