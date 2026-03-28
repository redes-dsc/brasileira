"""Verificação gramatical via LLM (tier PADRÃO)."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def check_grammar(text: str, router=None) -> dict:
    """Verifica e corrige gramática usando LLM.
    
    Args:
        text: Texto HTML do artigo
        router: SmartLLMRouter instance
    
    Returns:
        dict com: corrected_text, changes_made (bool), corrections (list)
    """
    if router is None:
        logger.warning("Router não disponível — retornando texto sem alterações")
        return {"corrected_text": text, "changes_made": False, "corrections": []}
    
    prompt = f"""Revise o texto jornalístico abaixo para erros gramaticais em português brasileiro.

REGRAS:
- Corrija APENAS erros gramaticais reais (concordância, regência, ortografia, acentuação)
- NÃO altere o estilo, tom ou estrutura do texto
- NÃO remova ou altere tags HTML (<p>, <h2>, <strong>, <a>, etc.)
- NÃO adicione informações que não estavam no original
- Se o texto estiver correto, retorne-o exatamente como está

Retorne APENAS o texto corrigido, sem comentários ou explicações.

TEXTO:
{text[:4000]}"""

    try:
        response = await router.complete(
            task_type="revisao_texto",
            messages=[
                {"role": "system", "content": "Você é um revisor gramatical do portal Brasileira.news. Corrija apenas erros reais de português."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000
        )
        
        corrected = response.get("content", text) if isinstance(response, dict) else str(response)
        changes_made = corrected.strip() != text.strip()
        
        return {
            "corrected_text": corrected,
            "changes_made": changes_made,
            "corrections": []  # TODO: diff para listar correções específicas
        }
    except Exception as e:
        logger.error("Grammar check LLM falhou: %s", e)
        return {"corrected_text": text, "changes_made": False, "corrections": []}
