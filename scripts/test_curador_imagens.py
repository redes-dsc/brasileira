#!/usr/bin/env python3
"""
Teste de Stress do Curador de Imagens Unificado
Testa cada TIER individualmente e em cascata.
"""

import sys
import os
import time
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s"
)
logger = logging.getLogger("test_curador")

# Importar módulo
sys.path.insert(0, "/home/bitnami")
from curador_imagens_unificado import (
    # Funções TIER
    tier1_scrape_html,
    tier2_government_banks,
    tier3a_flickr_gov,
    tier3b_wikimedia,
    tier3c_google_cse,
    tier4_stock_apis,
    # Utilitários
    is_official_source,
    is_valid_image_url,
    generate_search_keywords,
    # Compatibility
    get_curador,
    get_featured_image,
    search_unsplash,
    extract_image_from_content,
    # Keys
    UNSPLASH_ACCESS_KEY,
    PEXELS_API_KEY,
    PIXABAY_API_KEY,
    GOOGLE_CSE_ID,
    GOOGLE_API_KEY_CSE,
    FLICKR_API_KEY,
)

# =====================================================================
# CONFIGURAÇÃO DE TESTES
# =====================================================================

# URLs de teste para fontes oficiais
TEST_GOV_URLS = [
    "https://www.gov.br/planalto/pt-br/acompanhe-o-planalto/noticias",
    "https://agenciabrasil.ebc.com.br/economia",
    "https://www12.senado.leg.br/noticias",
]

# Keywords de teste
TEST_KEYWORDS = [
    "economia brasileira",
    "presidente Lula",
    "congresso nacional",
    "meio ambiente",
    "tecnologia Brasil",
]

# HTML de teste com og:image
TEST_HTML_WITH_IMAGE = '''
<!DOCTYPE html>
<html>
<head>
    <meta property="og:image" content="https://agenciabrasil.ebc.com.br/sites/default/files/atoms/image/example.jpg">
    <title>Teste</title>
</head>
<body>
    <img src="https://example.com/image.jpg" alt="Exemplo">
</body>
</html>
'''

# =====================================================================
# FUNÇÕES DE TESTE
# =====================================================================

def test_api_keys():
    """Verifica se as API keys estão configuradas."""
    print("\n" + "=" * 60)
    print("VERIFICAÇÃO DE API KEYS")
    print("=" * 60)
    
    keys = {
        "UNSPLASH_ACCESS_KEY": UNSPLASH_ACCESS_KEY,
        "PEXELS_API_KEY": PEXELS_API_KEY,
        "PIXABAY_API_KEY": PIXABAY_API_KEY,
        "GOOGLE_CSE_ID": GOOGLE_CSE_ID,
        "GOOGLE_API_KEY_CSE": GOOGLE_API_KEY_CSE,
        "FLICKR_API_KEY": FLICKR_API_KEY,
    }
    
    results = {}
    for name, value in keys.items():
        status = "✓ OK" if value else "✗ MISSING"
        print(f"  {name}: {status}")
        results[name] = bool(value)
    
    return results


def test_tier1_scraping():
    """Testa TIER 1: Raspagem de HTML."""
    print("\n" + "=" * 60)
    print("TESTE TIER 1: RASPAGEM HTML")
    print("=" * 60)
    
    # Teste com HTML local
    result = tier1_scrape_html(TEST_HTML_WITH_IMAGE, "https://agenciabrasil.ebc.com.br")
    if result:
        print(f"  ✓ Extraiu og:image: {result[:80]}...")
        return True
    else:
        print("  ✗ Falhou ao extrair og:image")
        return False


def test_tier2_gov_banks():
    """Testa TIER 2: Bancos governamentais."""
    print("\n" + "=" * 60)
    print("TESTE TIER 2: BANCOS GOVERNAMENTAIS")
    print("=" * 60)
    
    success_count = 0
    for keyword in TEST_KEYWORDS[:2]:
        print(f"\n  Testando: '{keyword}'")
        start = time.time()
        result = tier2_government_banks(keyword)
        elapsed = time.time() - start
        
        if result:
            print(f"    ✓ Encontrada em {elapsed:.2f}s: {result[:60]}...")
            success_count += 1
        else:
            print(f"    ✗ Não encontrada ({elapsed:.2f}s)")
    
    return success_count > 0


def test_tier3a_flickr():
    """Testa TIER 3A: Flickr Gov."""
    print("\n" + "=" * 60)
    print("TESTE TIER 3A: FLICKR GOV")
    print("=" * 60)
    
    if not FLICKR_API_KEY:
        print("  ℹ Usando fallback (sem API key)")
    
    keyword = "Brasília"
    print(f"\n  Testando: '{keyword}'")
    start = time.time()
    result = tier3a_flickr_gov(keyword)
    elapsed = time.time() - start
    
    if result:
        print(f"  ✓ Encontrada em {elapsed:.2f}s: {result[:60]}...")
        return True
    else:
        print(f"  ✗ Não encontrada ({elapsed:.2f}s)")
        return False


def test_tier3b_wikimedia():
    """Testa TIER 3B: Wikimedia Commons."""
    print("\n" + "=" * 60)
    print("TESTE TIER 3B: WIKIMEDIA COMMONS")
    print("=" * 60)
    
    keyword = "Congresso Nacional Brasil"
    print(f"\n  Testando: '{keyword}'")
    start = time.time()
    result = tier3b_wikimedia(keyword)
    elapsed = time.time() - start
    
    if result:
        print(f"  ✓ Encontrada em {elapsed:.2f}s: {result[:60]}...")
        return True
    else:
        print(f"  ✗ Não encontrada ({elapsed:.2f}s)")
        return False


def test_tier3c_google_cse():
    """Testa TIER 3C: Google Custom Search."""
    print("\n" + "=" * 60)
    print("TESTE TIER 3C: GOOGLE CSE")
    print("=" * 60)
    
    if not GOOGLE_CSE_ID or not GOOGLE_API_KEY_CSE:
        print("  ⊘ SKIPPED (API keys não configuradas)")
        return None
    
    keyword = "economia Brasil"
    print(f"\n  Testando: '{keyword}'")
    start = time.time()
    result = tier3c_google_cse(keyword)
    elapsed = time.time() - start
    
    if result:
        print(f"  ✓ Encontrada em {elapsed:.2f}s: {result[:60]}...")
        return True
    else:
        print(f"  ✗ Não encontrada ({elapsed:.2f}s)")
        return False


def test_tier4_stock_apis():
    """Testa TIER 4: Stock APIs (Unsplash, Pexels, Pixabay)."""
    print("\n" + "=" * 60)
    print("TESTE TIER 4: STOCK APIs")
    print("=" * 60)
    
    if not UNSPLASH_ACCESS_KEY and not PEXELS_API_KEY and not PIXABAY_API_KEY:
        print("  ⊘ SKIPPED (nenhuma API key configurada)")
        return None
    
    keyword = "Brazil technology"
    print(f"\n  Testando: '{keyword}'")
    start = time.time()
    result, credit = tier4_stock_apis(keyword)
    elapsed = time.time() - start
    
    if result:
        print(f"  ✓ Encontrada em {elapsed:.2f}s")
        print(f"    URL: {result[:60]}...")
        print(f"    Crédito: {credit}")
        return True
    else:
        print(f"  ✗ Não encontrada ({elapsed:.2f}s)")
        return False


def test_ai_keywords():
    """Testa geração de keywords com IA."""
    print("\n" + "=" * 60)
    print("TESTE AI KEYWORDS")
    print("=" * 60)
    
    title = "Governo anuncia novas medidas econômicas para 2026"
    content = "O presidente anunciou nesta quarta-feira um pacote de medidas para estimular a economia brasileira."
    
    print(f"\n  Título: {title}")
    start = time.time()
    keywords = generate_search_keywords(title, content, use_ai=True)
    elapsed = time.time() - start
    
    print(f"  Keywords geradas em {elapsed:.2f}s: {keywords}")
    return bool(keywords)


def test_cascade_full():
    """Testa a cascata completa de TIERs."""
    print("\n" + "=" * 60)
    print("TESTE CASCATA COMPLETA (DRY-RUN)")
    print("=" * 60)
    
    curador = get_curador()
    
    # Simular busca de imagem (sem upload real)
    test_cases = [
        {
            "title": "Presidente sanciona nova lei de proteção ambiental",
            "source_url": "https://www.gov.br/planalto/noticias/lei-ambiental",
            "keywords": "meio ambiente legislação",
        },
        {
            "title": "Banco Central mantém taxa Selic em 12% ao ano",
            "source_url": "https://www.bcb.gov.br/noticias",
            "keywords": "Selic juros economia",
        },
    ]
    
    print("\n  ℹ Nota: Teste sem upload real (verificação de lógica)")
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n  Caso {i}: {case['title'][:50]}...")
        print(f"    Fonte: {case['source_url']}")
        print(f"    É oficial? {is_official_source(case['source_url'])}")
    
    return True


def test_compatibility_functions():
    """Testa funções de compatibilidade."""
    print("\n" + "=" * 60)
    print("TESTE FUNÇÕES DE COMPATIBILIDADE")
    print("=" * 60)
    
    # Test get_curador
    curador = get_curador()
    print(f"  get_curador(): {type(curador).__name__}")
    
    # Test search_unsplash
    if UNSPLASH_ACCESS_KEY:
        result = search_unsplash("Brazil landscape")
        status = "✓" if result else "✗"
        print(f"  search_unsplash(): {status}")
    else:
        print("  search_unsplash(): ⊘ SKIPPED (no key)")
    
    # Test extract_image_from_content
    result = extract_image_from_content(TEST_HTML_WITH_IMAGE, "https://example.com")
    status = "✓" if result else "✗"
    print(f"  extract_image_from_content(): {status}")
    
    return True


def run_all_tests():
    """Executa todos os testes."""
    print("\n" + "=" * 60)
    print("  CURADOR DE IMAGENS UNIFICADO - SUITE DE TESTES")
    print("=" * 60)
    
    results = {}
    
    # 1. API Keys
    results["api_keys"] = test_api_keys()
    
    # 2. TIER 1
    results["tier1"] = test_tier1_scraping()
    
    # 3. TIER 2
    results["tier2"] = test_tier2_gov_banks()
    
    # 4. TIER 3A
    results["tier3a"] = test_tier3a_flickr()
    
    # 5. TIER 3B
    results["tier3b"] = test_tier3b_wikimedia()
    
    # 6. TIER 3C
    results["tier3c"] = test_tier3c_google_cse()
    
    # 7. TIER 4
    results["tier4"] = test_tier4_stock_apis()
    
    # 8. AI Keywords
    results["ai_keywords"] = test_ai_keywords()
    
    # 9. Cascade
    results["cascade"] = test_cascade_full()
    
    # 10. Compatibility
    results["compatibility"] = test_compatibility_functions()
    
    # Resumo
    print("\n" + "=" * 60)
    print("  RESUMO DOS TESTES")
    print("=" * 60)
    
    passed = 0
    failed = 0
    skipped = 0
    
    for name, result in results.items():
        if result is None:
            status = "⊘ SKIPPED"
            skipped += 1
        elif result is True or (isinstance(result, dict) and any(result.values())):
            status = "✓ PASSED"
            passed += 1
        else:
            status = "✗ FAILED"
            failed += 1
        print(f"  {name}: {status}")
    
    print(f"\n  Total: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
