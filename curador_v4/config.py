"""Configuração centralizada do Curador V4 via variáveis de ambiente."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


# Mapeamento padrão de editorias (category_id → label)
DEFAULT_EDITORIAS: dict[int, str] = {
    15285: "Política & Poder",
    15661: "Economia & Negócios",
    15410: "Tecnologia",
    88: "Internacional",
    11931: "Entretenimento",
    11989: "Esportes",
    15652: "Sustentabilidade",
    79: "Cultura",
    129: "Ciência & Inovação",
    15653: "Saúde",
    15654: "Educação",
    15655: "Segurança & Justiça",
    15656: "Sociedade",
    15657: "Brasil",
    15658: "Opinião & Análise",
    15659: "Últimas Notícias",
}


@dataclass
class CuradorConfig:
    """Configuração completa do Curador V4."""

    # WordPress
    wp_base_url: str = "https://brasileira.news"
    wp_user: str = "iapublicador"
    wp_app_password: str = ""
    homepage_page_id: int = 18135

    # LLM (via LiteLLM proxy)
    litellm_base_url: str = "http://localhost:4000"
    litellm_api_key: str = ""
    llm_model: str = "premium"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Supabase (logging)
    supabase_url: str = ""
    supabase_key: str = ""

    # Intervalos de ciclo por período (segundos)
    cycle_interval_nobre: int = 900     # 15 min — horário nobre
    cycle_interval_normal: int = 1800   # 30 min — matinal/vespertino
    cycle_interval_noturno: int = 3600  # 60 min — noturno

    # Limiares
    breaking_urgency_threshold: float = 0.85
    macrotema_min_posts: int = 5
    macrotema_min_categories: int = 2
    min_posts_per_editoria: int = 3
    scan_hours_back: int = 4

    # Editorias (category_id → label)
    editorias: dict[int, str] = field(default_factory=lambda: dict(DEFAULT_EDITORIAS))


def load_config() -> CuradorConfig:
    """Carrega configuração a partir de variáveis de ambiente."""

    # Editorias: aceita JSON customizado ou usa padrão
    editorias_raw = os.getenv("EDITORIAS_JSON", "").strip()
    if editorias_raw:
        try:
            editorias = {int(k): str(v) for k, v in json.loads(editorias_raw).items()}
        except (json.JSONDecodeError, ValueError):
            editorias = dict(DEFAULT_EDITORIAS)
    else:
        editorias = dict(DEFAULT_EDITORIAS)

    return CuradorConfig(
        wp_base_url=os.getenv("WP_URL", "https://brasileira.news"),
        wp_user=os.getenv("WP_USER", "iapublicador"),
        wp_app_password=os.getenv("WP_AUTH") or os.getenv("WP_APP_PASS", ""),
        homepage_page_id=int(os.getenv("HOMEPAGE_PAGE_ID", "18135")),
        litellm_base_url=os.getenv("LITELLM_BASE_URL", "http://localhost:4000"),
        litellm_api_key=os.getenv("LITELLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "premium"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        supabase_url=os.getenv("SUPABASE_URL", ""),
        supabase_key=os.getenv("SUPABASE_KEY", ""),
        cycle_interval_nobre=int(os.getenv("CYCLE_INTERVAL_NOBRE", "900")),
        cycle_interval_normal=int(os.getenv("CYCLE_INTERVAL_NORMAL", "1800")),
        cycle_interval_noturno=int(os.getenv("CYCLE_INTERVAL_NOTURNO", "3600")),
        breaking_urgency_threshold=float(os.getenv("BREAKING_URGENCY_THRESHOLD", "0.85")),
        macrotema_min_posts=int(os.getenv("MACROTEMA_MIN_POSTS", "5")),
        macrotema_min_categories=int(os.getenv("MACROTEMA_MIN_CATEGORIES", "2")),
        min_posts_per_editoria=int(os.getenv("MIN_POSTS_PER_EDITORIA", "3")),
        scan_hours_back=int(os.getenv("SCAN_HOURS_BACK", "4")),
        editorias=editorias,
    )
