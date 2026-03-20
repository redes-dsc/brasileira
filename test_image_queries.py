import sys
import os

sys.path.append("/home/bitnami")
from curador_imagens_unificado import get_query_generator

def test_news(title, content):
    print(f"\n--- Testando: {title} ---")
    gen = get_query_generator()
    cat = gen._detect_category(title, content)
    print(f"Categoria dectectada: {cat}")
    queries = gen._generate_ai_queries(title, content, cat)
    print(f"Resultado Gemini:")
    if queries:
        for k, v in queries.items():
            print(f"  {k}: {v}")
    else:
        print("  Falha ao gerar queries com IA")

if __name__ == "__main__":
    test_news(
        "Vasco vence Fluminense em partida emocionante que desafia certezas",
        "O Vasco garantiu a vitória no clássico carioca contra o Fluminense por 2 a 1, com gols no segundo tempo. O jogo aconteceu no Maracanã e teve muita disputa de bola."
    )
    
    test_news(
        "Conflito entre diretores de Palmeiras e São Paulo esquenta clima pré-jogo",
        "A presidente Leila Pereira, do Palmeiras, e o presidente Julio Casares, do São Paulo, trocaram farpas na imprensa sobre a arbitragem do último clássico no Morumbi."
    )
    
    test_news(
        "Lula critica corte de 0,25% da Selic: 'Porra, essa guerra até...'",
        "O presidente Luiz Inácio Lula da Silva voltou a criticar o Banco Central e Roberto Campos Neto pelo ritmo baixo de corte na taxa básica de juros, a Selic."
    )
    
    test_news(
        "Moise Kouame se torna o mais jovem vencedor do Masters de Madrid",
        "O jovem tenista Moise Kouame fez história ao vencer o torneio de Madrid com apenas 18 anos, derrotando grandes nomes do esporte na quadra."
    )

    test_news(
        "Petróleo: Ataques a instalações geram turbulência e alta nos preços",
        "Ataques a instalações petrolíferas no Irã durante a madrugada elevaram o preço do barril de petróleo no mercado internacional."
    )
