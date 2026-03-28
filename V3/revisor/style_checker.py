"""Verificação de estilo editorial via LLM (tier PADRÃO)."""

import logging

logger = logging.getLogger(__name__)


async def check_style(text: str, titulo: str, router=None) -> dict:
    """Verifica estilo editorial usando LLM.
    
    Baseado nas regras de regras_editoriais.py da V1:
    - Limpeza chapa-branca
    - Presunção de inocência
    - Números por extenso (0-10)
    - Moedas: R$ formato correto
    - Sem linguagem promocional
    """
    if router is None:
        return {"corrected_text": text, "style_issues": [], "changes_made": False}
    
    prompt = f"""Revise o estilo editorial do texto abaixo seguindo o manual de redação:

REGRAS DO MANUAL:
1. CHAPA-BRANCA: Transforme linguagem promocional de governos em relato objetivo
2. PRESUNÇÃO DE INOCÊNCIA: Use "suspeito de", "acusado de" (nunca afirmar culpa)
3. NÚMEROS: Por extenso de zero a dez, numerais a partir de 11
4. MOEDAS: R$ antes do número. Acima de mil: "R$ 1,5 milhão"
5. SIGLAS: Na primeira menção, nome completo seguido da sigla entre parênteses
6. ASPAS: Só para citações reais — NUNCA inventar aspas
7. Tom neutro e informativo, sem adjetivos desnecessários

NÃO altere tags HTML. Retorne APENAS o texto corrigido.

TÍTULO: {titulo}

TEXTO:
{text[:4000]}"""

    try:
        response = await router.complete(
            task_type="revisao_texto",
            messages=[
                {"role": "system", "content": "Você é o editor de estilo do portal Brasileira.news. Aplique o manual de redação sem alterar a estrutura HTML."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000
        )
        
        corrected = response.get("content", text) if isinstance(response, dict) else str(response)
        changes_made = corrected.strip() != text.strip()
        
        return {
            "corrected_text": corrected,
            "style_issues": [],
            "changes_made": changes_made
        }
    except Exception as e:
        logger.error("Style check LLM falhou: %s", e)
        return {"corrected_text": text, "style_issues": [], "changes_made": False}
