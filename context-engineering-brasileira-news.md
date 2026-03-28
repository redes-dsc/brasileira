# Diretrizes de Context Engineering para o Sistema Multi-Agente — brasileira.news

**Versão:** 1.1 — Atualizada com implementação V2  
**Data:** 23 de março de 2026  
**Classificação:** Técnico-Estratégico — Documento de Referência  
**Público-alvo:** Equipe de Desenvolvimento / Arquiteto de IA  
**Escopo:** Aplicação prática de context engineering no sistema multi-agente V2 do brasileira.news  
**Status V2:** 15+ agentes LangGraph · LiteLLM Gateway (104 modelos, 7 provedores, 34 chaves) · EventBus Redis · Memória 3 camadas  

---

## Sumário Executivo

Context engineering é a disciplina de projetar e gerenciar o ambiente informacional que alimenta modelos de linguagem — determinando quais informações o modelo vê, quando vê e em que formato. Diferente de prompt engineering, que se concentra em redigir instruções para uma interação pontual, context engineering trata do **sistema inteiro** que preenche a janela de contexto: memória, recuperação, ferramentas, histórico e, sim, o prompt ([Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)). Como [Andrej Karpathy](https://x.com/karpathy/status/1937902205765607626) sintetizou: "O LLM é como a CPU e sua janela de contexto é como a RAM — context engineering é a arte e ciência de preencher essa memória de trabalho com exatamente a informação certa para o próximo passo."

Para o brasileira.news — um sistema multi-agente **já implementado** com 15+ agentes LangGraph hierárquicos (Diretor de Redação → Editores → Repórteres → Focas), processando 1.000+ artigos/dia a partir de 630+ fontes, com roteamento LLM de 4 tiers via LiteLLM Gateway (104 modelos, 7 provedores, 34 chaves API) — context engineering não é opcional. É a diferença entre agentes que produzem o milésimo artigo com a mesma qualidade do primeiro e agentes que degradam progressivamente por context rot, envenenamento de contexto ou confusão entre ferramentas ([Firecrawl](https://www.firecrawl.dev/blog/context-engineering)).

A auditoria de 329 bugs do codebase atual revela que **muitos problemas já são falhas de context engineering** antes de serem bugs de código: prompts contraditórios entre `roteador_ia.py` e `llm_router.py`, dois `curator_config.py` incompatíveis coexistindo, credenciais hardcoded que poluem logs e comandos de processo, e acúmulo de histórico sem compressão que esgota memória RAM. Este documento traduz princípios de context engineering em diretrizes concretas para a nova arquitetura.

---

## 1. Fundamentos: O Modelo Mental

### 1.1 Contexto como Recurso Finito

A janela de contexto de um LLM é um recurso escasso com retornos decrescentes. O princípio orientador é encontrar o **menor conjunto possível de tokens de alto sinal** que maximize a probabilidade do resultado desejado ([Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)). Mais tokens nem sempre significam melhores resultados — à medida que o volume aumenta, a atenção do modelo se dilui.

Para o brasileira.news operando a 1.000+ artigos/dia, isso se traduz em: cada agente (Diretor, Editor, Repórter, etc.) deve operar com a **quantidade mínima de contexto necessária para sua tarefa específica**, e nada mais.

### 1.2 O Orçamento de Atenção

LLMs possuem um "orçamento de atenção" limitado — sua memória de trabalho ativa. Assim como um editor humano não consegue ler 200 matérias simultaneamente e decidir bem sobre cada uma, um LLM sobrecarregado com tokens irrelevantes perde acurácia. Estudos de benchmark needle-in-a-haystack demonstram que a capacidade do modelo de localizar informação específica **degrada conforme o contexto cresce** ([Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents), [Elastic](https://www.elastic.co/search-labs/blog/context-engineering-llm-evolution-agentic-ai)).

**Implicação prática:** O Diretor de Redação não precisa ver o conteúdo completo de 200 artigos para decidir quais são tendência — precisa de metadados (título, fonte, categoria, score de relevância). O Repórter não precisa do histórico de todos os artigos da semana — precisa do briefing da pauta e das fontes primárias.

### 1.3 Separação entre Contexto Estático e Dinâmico

| Tipo | Posição no Prompt | Componentes | Benefícios |
|---|---|---|---|
| **Contexto de Decisão (Estático)** | Início do prompt | Padrões editoriais, regras de categorização, taxonomia de 16 macrocategorias e 73 subcategorias, guidelines de tom e voz, políticas de imagem | Permite prompt caching (até 90% de economia em tokens) ([Firecrawl](https://www.firecrawl.dev/blog/context-engineering)) |
| **Contexto Operacional (Dinâmico)** | Final do prompt | Estado atual do ciclo, artigos em processamento, métricas de quota de API, alertas de fontes offline, dados em tempo real | Aproveita viés de recência para atenção forte ([Firecrawl](https://www.firecrawl.dev/blog/context-engineering)) |

No sistema atual, essa separação não existe: `roteador_ia.py` e `llm_router.py` misturam configurações estáticas (lista de provedores) com estado dinâmico (circuit breaker), e as regras editoriais estão espalhadas em múltiplos arquivos Python sem hierarquia clara.

---

## 2. As Quatro Estratégias Fundamentais: Write / Select / Compress / Isolate

O framework Write/Select/Compress/Isolate, consolidado por [LangChain](https://blog.langchain.com/context-engineering-for-agents/) e amplamente adotado pela indústria ([Kubiya](https://www.kubiya.ai/blog/context-engineering-best-practices), [Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)), organiza todas as técnicas de context engineering em quatro estratégias complementares.

### 2.1 WRITE — Escrever Contexto (Persistir Fora da Janela)

**Definição:** Salvar informações fora da janela de contexto imediata para que possam ser acessadas e reutilizadas em passos ou sessões posteriores ([Kubiya](https://www.kubiya.ai/blog/context-engineering-best-practices)).

#### 2.1.1 Scratchpads (Blocos de Rascunho)

Servem como memória de trabalho intermediária. Em vez de regenerar ou repetir informações, o agente consulta o scratchpad para recuperar detalhes relevantes.

**Aplicação no brasileira.news:**

| Agente | Scratchpad | Conteúdo | Formato |
|---|---|---|---|
| Diretor de Redação | `plano_editorial_{data}.json` | Temas prioritários, cotas por editoria, alertas de tendências, decisões de destaque | JSON estruturado em Redis (TTL: 24h) |
| Editor-Chefe | `pauta_ciclo_{timestamp}.json` | Matérias selecionadas, assignments para editores, critérios de priorização do ciclo | JSON em Redis (TTL: 4h) |
| Pauteiro | `radar_fontes_{ciclo}.json` | Fontes processadas, artigos candidatos, scores de relevância TF-IDF | JSON em Redis (TTL: 2h) |
| Editor de Fotografia | `decisoes_imagem_{ciclo}.json` | Imagens selecionadas por tier, quotas CSE consumidas, fallbacks acionados | JSON em Redis (TTL: 1h) |

**Correção de bug existente:** O `historico_links.txt` — carregado inteiro em RAM 34 vezes por ciclo (Bug #M-14 da auditoria) — deve migrar para uma tabela indexada no PostgreSQL, consultada por query pontual, não por leitura completa de arquivo.

#### 2.1.2 Memórias de Longo Prazo

Persistem entre sessões e acumulam conhecimento editorial ao longo do tempo.

**Camadas de memória para o brasileira.news:**

| Tipo de Memória | O Que Armazena | Exemplo Humano | Exemplo no Sistema | Storage |
|---|---|---|---|---|
| **Semântica** | Fatos e conhecimento de domínio | "O que aprendi na escola" | Taxonomia de 16 categorias, perfil de cada fonte, padrões de cada portal | pgvector (PostgreSQL) |
| **Episódica** | Experiências passadas | "O que eu fiz ontem" | Histórico de decisões editoriais, artigos que performaram bem/mal, fontes que falharam | PostgreSQL + embeddings |
| **Procedural** | Instruções e rotinas | "Como eu faço isso" | System prompts dos agentes, regras de roteamento LLM, pipeline de imagens | Arquivos versionados (Git) |

Referência: Esta taxonomia de memória é consistente com as categorizações de [Weaviate](https://weaviate.io/blog/context-engineering) e [Kubiya](https://www.kubiya.ai/blog/context-engineering-best-practices).

**Implementação concreta:**

```python
# Exemplo: Agente "Diretor de Redação" escrevendo memória episódica
async def registrar_decisao_editorial(decisao: dict):
    """Persiste decisão editorial para aprendizado futuro."""
    embedding = await gerar_embedding(decisao["resumo"])
    await pgvector.insert(
        tabela="memoria_editorial",
        dados={
            "agente": "diretor_redacao",
            "tipo": "episodica",
            "conteudo": decisao,
            "embedding": embedding,
            "timestamp": datetime.now(tz=ZoneInfo("America/Sao_Paulo")),
            "relevancia_score": decisao.get("score", 0.5),
            "ttl_dias": 90  # Memórias editoriais expiram em 90 dias
        }
    )
```

#### 2.1.3 Checkpointing

Técnica de persistência seletiva do estado para manter contexto relevante e filtrar dados obsoletos.

**Aplicação:** Cada ciclo de processamento (a cada 30 minutos para RSS, 2 horas para Consolidado) deve gerar um checkpoint com:
- Artigos processados (IDs, não conteúdo completo)
- Decisões de roteamento LLM tomadas (qual tier, por quê)
- Erros encontrados e como foram tratados
- Métricas de quota consumida por provedor

Isso resolve diretamente o bug de `cloudscraper` instanciado por request sem cleanup — cada checkpoint inclui a liberação explícita de recursos.

### 2.2 SELECT — Selecionar Contexto (Recuperar o que Importa)

**Definição:** Puxar para dentro da janela de contexto apenas a informação mais pertinente para a tarefa atual, reduzindo consumo de tokens e mantendo o foco do agente ([LangChain](https://blog.langchain.com/context-engineering-for-agents/)).

#### 2.2.1 Recuperação Just-in-Time

Em vez de pré-carregar todo o contexto possível, manter **identificadores leves** (caminhos de arquivo, queries armazenadas, URLs) e carregar dados dinamicamente em tempo de execução usando ferramentas ([Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)).

**Padrão para o brasileira.news:**

```
❌ ERRADO (sistema atual):
   Motor Consolidado carrega historico_links.txt inteiro (milhares de URLs)
   em RAM para verificar duplicatas → 34 vezes por ciclo

✅ CORRETO (nova arquitetura):
   Motor Consolidado mantém referência à tabela `artigos_processados`
   e executa: SELECT 1 FROM artigos_processados WHERE url_hash = $1
   → Uma query por verificação, zero carga em memória
```

**Implementação no LangGraph:**

```python
# Ferramenta de seleção just-in-time para o agente Pauteiro
@tool
def verificar_duplicata(url: str) -> bool:
    """Verifica se uma URL já foi processada. Retorna True se duplicata."""
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    resultado = db.execute(
        "SELECT 1 FROM artigos_processados WHERE url_hash = %s",
        (url_hash,)
    )
    return resultado.fetchone() is not None
```

#### 2.2.2 Divulgação Progressiva (Progressive Disclosure)

Agentes descobrem contexto incrementalmente através de exploração. Cada interação fornece contexto que informa a próxima decisão: nomes de fontes sugerem categoria; timestamps indicam frescor; tamanho do conteúdo sugere complexidade ([Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)).

**Fluxo para o Pauteiro:**

```
Passo 1: Consulta radar de fontes → recebe lista de 50 artigos candidatos
         (apenas: título, fonte, categoria, timestamp, score)
Passo 2: Seleciona 15 mais relevantes → solicita resumos expandidos
         (agora: título, fonte, lide, palavras-chave, entidades nomeadas)
Passo 3: Agrupa por tendência → solicita conteúdo completo dos 5 top
         (agora: texto integral para análise profunda)
```

Em nenhum momento o Pauteiro carrega 50 artigos completos na janela de contexto.

#### 2.2.3 Seleção de Ferramentas via RAG

Quando um agente tem acesso a muitas ferramentas, a probabilidade de selecionar a errada aumenta. Pesquisas demonstram que aplicar RAG sobre descrições de ferramentas melhora a acurácia de seleção em até 3x ([LangChain](https://blog.langchain.com/context-engineering-for-agents/)). A [Firecrawl](https://www.firecrawl.dev/blog/context-engineering) reportou que um modelo Llama 3.1 8b falhou com 46 ferramentas mas funcionou com 19.

**Diretriz para brasileira.news:** Cada papel de agente deve ter no máximo **15-20 ferramentas ativas** por passo. Para o Repórter (que interage com scraping, LLM, WordPress API, imagens), dividir em sub-ferramentas contextuais:

| Fase do Repórter | Ferramentas Ativas | Total |
|---|---|---|
| Coleta de fonte | `fetch_rss`, `scrape_html`, `scrape_nextjs`, `parse_api`, `parse_sitemap` | 5 |
| Processamento editorial | `gerar_titulo`, `gerar_resumo`, `classificar_categoria`, `extrair_entidades`, `verificar_duplicata` | 5 |
| Enriquecimento | `buscar_imagem`, `gerar_tags`, `gerar_slug`, `validar_conteudo` | 4 |
| Publicação | `publicar_wp`, `atualizar_status`, `registrar_metrica` | 3 |

#### 2.2.4 Recuperação Híbrida para Knowledge Base

Para a base de conhecimento vetorial (pgvector), combinar múltiplas estratégias de busca:

```
Consulta do Editor
        │
        ├─→ Busca por embedding (semântica) ─────┐
        │                                        │
        ├─→ Busca por keyword (BM25/trigram) ────┼─→ Re-ranking ─→ Top-K resultados
        │                                        │
        └─→ Busca por metadados (fonte, data) ───┘
```

A estratégia de chunking impacta diretamente a qualidade ([Weaviate](https://weaviate.io/blog/context-engineering)):

| Tamanho do Chunk | Prós | Contras |
|---|---|---|
| **Pequeno** (256-512 tokens) | Precisão alta; embeddings focados | Falta contexto circundante para o LLM |
| **Grande** (1024-2048 tokens) | Rico em contexto para geração | Embeddings "ruidosos"; ocupa mais espaço na janela |
| **Adaptativo** (por parágrafo/seção) | Melhor equilíbrio | Mais complexo de implementar |

**Recomendação:** Chunks de 512 tokens com overlap de 128 tokens para artigos jornalísticos. Para o `catalogo_fontes.py` (398 fontes em 23 gavetas), indexar cada fonte como um documento separado com metadados estruturados.

### 2.3 COMPRESS — Comprimir Contexto (Reter Apenas o Essencial)

**Definição:** Reduzir a quantidade de informação passada a um agente sem perder detalhes críticos, otimizando eficiência de tokens, acelerando processamento e mantendo foco ([Kubiya](https://www.kubiya.ai/blog/context-engineering-best-practices)).

#### 2.3.1 Sumarização Hierárquica

Para interações longas ou saídas pesadas de ferramentas. Usa abordagens recursivas para extrair mensagens-chave passo a passo.

**Aplicação no brasileira.news — Handoff entre agentes:**

```
Pauteiro processa 200 artigos candidatos
    │
    ├─→ Sumarização: "15 artigos selecionados em 5 tendências"
    │   (200 artigos → 15 resumos de 100 tokens cada = 1.500 tokens)
    │
    └─→ Handoff para Editor-Chefe
         (recebe 1.500 tokens, não 200.000)
```

A [Cognition.ai](https://www.kubiya.ai/blog/context-engineering-best-practices) demonstrou que sumarizar handoffs entre agentes reduz drasticamente o consumo de tokens em sistemas multi-agente. Modelos fine-tuned para sumarização produzem resultados mais precisos que prompts genéricos.

#### 2.3.2 Compactação (Compaction)

Para tarefas que requerem fluxo conversacional extenso. Quando o agente se aproxima do limite da janela de contexto, o histórico é passado ao modelo para sumarização, preservando decisões arquiteturais e bugs não resolvidos, descartando outputs redundantes de ferramentas ([Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)).

**Implementação inspirada no Claude Code:**

```python
async def compactar_contexto(mensagens: list, limiar: float = 0.85):
    """Compacta quando uso da janela atinge 85% do limite."""
    tokens_usados = contar_tokens(mensagens)
    tokens_max = MODELO_CONFIG[modelo_atual]["context_window"]
    
    if tokens_usados / tokens_max >= limiar:
        # Preservar: decisões editoriais, erros pendentes, estado atual
        # Descartar: outputs crus de ferramentas, conversas redundantes
        resumo = await llm.sumarizar(
            mensagens=mensagens,
            instrucao="""Preserve:
            - Decisões editoriais tomadas e justificativas
            - Artigos em processamento (IDs e status)
            - Erros não resolvidos e workarounds aplicados
            - Estado de quotas de API
            Descarte:
            - Outputs completos de scraping já processados
            - Tentativas de fallback que já foram resolvidas
            - Metadados redundantes de fontes já catalogadas"""
        )
        # Manter resumo + 5 mensagens mais recentes
        return [resumo] + mensagens[-5:]
    return mensagens
```

#### 2.3.3 Limpeza de Resultados de Ferramentas (Tool Result Clearing)

A técnica mais segura e leve de compressão. Limpa os resultados brutos de chamadas de ferramentas que estão profundos no histórico, mantendo apenas a informação derivada ([Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)).

**Exemplo concreto:**

```
Antes da limpeza:
  [tool_call] scrape_html("https://g1.globo.com/article/...")
  [tool_result] { "html": "<!DOCTYPE html>...(15.000 tokens)...", 
                  "status": 200, "headers": {...} }
  [assistant] Artigo processado: "Governo anuncia novo pacote fiscal"

Após limpeza:
  [tool_call] scrape_html("https://g1.globo.com/article/...")
  [tool_result] <cleared>
  [assistant] Artigo processado: "Governo anuncia novo pacote fiscal"
```

**Diretriz:** Limpar tool results após 3 mensagens subsequentes ou quando o resultado já foi processado e a informação derivada está disponível no contexto.

#### 2.3.4 Trimming (Poda Heurística)

Filtragem baseada em regras para remover mensagens desatualizadas ou irrelevantes. Complementa a sumarização como operação leve.

**Regras para o brasileira.news:**

1. Mensagens de ciclos anteriores (>4h para RSS, >6h para Consolidado): podar
2. Logs de debug com status 200: podar após o ciclo
3. Metadados de fontes processadas com sucesso: manter apenas contagem
4. Erros transitórios resolvidos (timeout, 429): podar após retry bem-sucedido
5. Erros persistentes (fonte offline >24h): manter para decisão editorial

### 2.4 ISOLATE — Isolar Contexto (Compartimentalizar)

**Definição:** Dividir o contexto em compartimentos independentes para prevenir interferência, reduzir ruído e melhorar performance. Cada componente opera com exatamente os dados necessários sem contaminação cruzada ([Kubiya](https://www.kubiya.ai/blog/context-engineering-best-practices)).

#### 2.4.1 Arquitetura Multi-Agente com Isolamento

O padrão mais poderoso de isolamento. Subagentes especializados possuem janelas de contexto próprias, ferramentas específicas e instruções isoladas ([LangChain](https://blog.langchain.com/context-engineering-for-agents/), [Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)).

**Hierarquia editorial com isolamento de contexto:**

```
┌────────────────────────────────────────────────────────────┐
│  CAMADA SUPERVISÃO                                          │
│  DiretorRedacao: plano editorial + métricas macro           │
│  Janela: ~8K tokens · Tier: PREMIUM                        │
├────────────────────────────────────────────────────────────┤
│  CAMADA EDITORIAL                                           │
│  EditorChefe → EditorEditoria (por seção)                   │
│  ConsolidadorAgent (síntese multi-fonte)                    │
│  Janela: ~16K tokens · Tier: PREMIUM/REDACAO               │
├────────────┬────────────┬────────────┬─────────────────────┤
│ CuradorHome│CuradorSecao│CuradorSecao│ CuradorSecao        │
│ 19 posições│ Política   │ Economia   │ Esportes (+11)      │
│ homepage   │ cat:{71,   │ cat:{72,   │ cat:{75}            │
│ URGENTE    │ 11742}     │ 11755}     │                     │
│ fast-track │ ~12K tok   │ ~12K tok   │ ~12K tok            │
├────────────┴────────────┴────────────┴─────────────────────┤
│  CAMADA PRODUÇÃO                                            │
│  Reporter · Revisor (validação TIER 1) · Fotografo          │
│  Janela: ~32K tokens · Tier: REDACAO                        │
├────────────────────────────────────────────────────────────┤
│  CAMADA FONTE + MONITORAMENTO                               │
│  FocasAgent (554 fontes) · Pauteiro                         │
│  MonitorConcorrencia · AnalistaMetricas                     │
│  Janela: ~16K tokens · Tier: ECONOMICO                      │
└────────────────────────────────────────────────────────────┘

EventBus (Redis pub/sub) — Canais isolados por camada:
  nova_noticia → pauta_atribuida → artigo_publicado
  trending_cluster → artigo_consolidado
  urgente_queue → homepage refresh imediato
```

**Princípio-chave:** Subagentes exploram extensivamente (dezenas de milhares de tokens) mas retornam um **resumo condensado** de 1.000-2.000 tokens ao agente superior ([Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)). Isso atinge separação de concerns: contexto detalhado de busca isolado no subagente; agente líder sintetiza e analisa.

#### 2.4.2 Ambientes Sandboxed

Executar chamadas pesadas/arriscadas de ferramentas em ambientes externos, retornando apenas outputs limpos e concisos. O agente recebe valores de retorno e nomes de variáveis, não objetos completos como imagens ou documentos inteiros ([LangChain](https://blog.langchain.com/context-engineering-for-agents/)).

**Aplicação no pipeline de imagens:**

```python
# ❌ ERRADO: Imagem binária + metadados HTTP entram no contexto
resultado = await buscar_imagem_flickr(query="brasilia congresso")
# resultado contém: bytes da imagem, headers HTTP, metadados EXIF
# → Polui o contexto com milhares de tokens irrelevantes

# ✅ CORRETO: Sandbox processa e retorna apenas referência
resultado = await sandbox_imagem.processar({
    "acao": "buscar_e_validar",
    "query": "brasilia congresso",
    "tiers": [1, 2, 3]
})
# resultado contém apenas: 
# {"url": "https://...", "tier_usado": 2, "dimensoes": "800x600", "licenca": "CC-BY"}
# → 50 tokens limpos no contexto
```

Isso corrige diretamente o bug de `is_valid_image_url` fazendo HTTP HEAD por cada tag `<img>` — a validação ocorre no sandbox, e o agente recebe apenas o veredito.

#### 2.4.3 Objetos de Estado Modular

Estruturar o estado de runtime como objetos modulares com campos separados para mensagens, outputs de ferramentas e metadados. Expor apenas fatias relevantes por passo ([LangChain](https://blog.langchain.com/context-engineering-for-agents/), [Kubiya](https://www.kubiya.ai/blog/context-engineering-best-practices)).

**Schema de estado no LangGraph para o brasileira.news:**

```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph

class EstadoCicloEditorial(TypedDict):
    # Visível para todos os agentes (global state)
    ciclo_id: str
    timestamp_inicio: str
    plano_editorial: dict  # Do Diretor
    
    # Visível apenas para agentes de ingestão
    artigos_candidatos: list[dict]  # Metadados, não conteúdo
    fontes_processadas: list[str]   # Apenas IDs
    
    # Visível apenas para agentes de publicação
    artigos_aprovados: list[dict]
    fila_publicacao: list[dict]
    
    # Visível apenas para monitoramento
    metricas_quota: dict
    erros_ciclo: list[dict]
    
    # NUNCA exposto ao LLM diretamente
    _tokens_consumidos: int
    _custos_acumulados: float
    _logs_debug: list[str]
```

#### 2.4.4 Protocolos de Comunicação Inter-Agente

A comunicação entre agentes isolados deve seguir protocolos claros para evitar vazamento de contexto:

```
┌──────────┐    Resumo condensado     ┌──────────────┐
│ Pauteiro │ ──────────────────────── │ Editor-Chefe │
│          │  (1.500 tokens max)      │              │
│ Processa │                          │ Decide:      │
│ 200 arts │    Feedback estruturado  │ - Aprovações │
│          │ ◄──────────────────────  │ - Rejeições  │
└──────────┘    (200 tokens max)      └──────────────┘
```

**Formato de handoff padronizado:**

```json
{
  "de": "pauteiro",
  "para": "editor_chefe",
  "ciclo": "2026-03-23T22:00:00-03:00",
  "resumo": "200 artigos processados de 45 fontes. 15 selecionados.",
  "tendencias": [
    {"tema": "Reforma tributária", "artigos": 4, "score_medio": 0.87},
    {"tema": "Copa do Mundo", "artigos": 3, "score_medio": 0.82}
  ],
  "artigos_selecionados": [
    {"id": "art_001", "titulo": "...", "fonte": "G1", "score": 0.92},
    ...
  ],
  "alertas": ["Fonte Folha offline há 2 ciclos"],
  "tokens_totais": 1247
}
```

---

## 3. Modos de Falha de Contexto

Sistemas multi-agente são vulneráveis a quatro modos de falha de contexto documentados pela literatura ([Weaviate](https://weaviate.io/blog/context-engineering), [Firecrawl](https://www.firecrawl.dev/blog/context-engineering), [Kubiya](https://www.kubiya.ai/blog/context-engineering-best-practices)). A auditoria de 329 bugs do brasileira.news já exibe instâncias de todos eles.

### 3.1 Context Poisoning (Envenenamento de Contexto)

**Definição:** Erro ou alucinação entra no contexto e é repetidamente referenciado, contaminando a compreensão do sistema e levando a fixação em informações falsas ([Weaviate](https://weaviate.io/blog/context-engineering)).

**Exemplos já existentes no brasileira.news:**
- Flickr: usuários governamentais que são placeholders falsos (usernames como `us_government`, `uk_parliament`) retornam imagens irrelevantes que são tratadas como válidas pelo pipeline
- `catalogo_fontes.py` com URLs obsoletas de fontes que mudaram de domínio — o motor continua tentando, gerando erros que acumulam no contexto
- `agente_newspaper.py` com SQL injection no campo `post_title` — dados maliciosos de fontes externas podem entrar na base e ser processados por agentes downstream

**Mitigações:**

| Técnica | Implementação | Quando Aplicar |
|---|---|---|
| **Validação e quarentena** | Isolar tipos de contexto em threads separados; validar antes de admitir na memória de longo prazo | Toda ingestão de dados externos |
| **Detecção de anomalia** | Score de confiança em outputs de LLM; rejeitar abaixo de limiar | Geração de títulos, resumos, classificações |
| **Thread limpo** | Iniciar novo thread quando envenenamento detectado | Quando outputs consecutivos divergem >2σ da média |
| **Checksums semânticos** | Comparar embedding do output com embeddings esperados para a categoria | Classificação de artigos em 16 macrocategorias |

```python
# Exemplo: Validação anti-poisoning na classificação
async def classificar_artigo_seguro(artigo: dict) -> dict:
    classificacao = await llm.classificar(artigo)
    
    # Verificar consistência semântica
    embedding_artigo = await gerar_embedding(artigo["titulo"] + artigo["lide"])
    embedding_categoria = EMBEDDINGS_CATEGORIAS[classificacao["categoria"]]
    similaridade = cosine_similarity(embedding_artigo, embedding_categoria)
    
    if similaridade < 0.3:
        # Possível poisoning: categoria muito distante do conteúdo
        logger.warning(f"Possível poisoning: {artigo['titulo']} → "
                      f"{classificacao['categoria']} (sim={similaridade:.2f})")
        # Reclassificar com modelo mais forte (tier superior)
        classificacao = await llm.classificar(artigo, tier="premium")
    
    return classificacao
```

### 3.2 Context Distraction (Distração de Contexto)

**Definição:** Contexto acumulado faz o modelo focar excessivamente em dados históricos, repetindo ações passadas em vez de adotar estratégias novas, degradando efetividade ([Weaviate](https://weaviate.io/blog/context-engineering)).

**Exemplos no brasileira.news:**
- O motor consolidado que roda TF-IDF + clustering a cada 2 horas acumula histórico de artigos processados — se o contexto não for comprimido, o modelo pode re-sintetizar tendências já cobertas
- O curador de homepage com pontuação bifásica (objetiva + LLM): se o histórico de pontuações anteriores ficar no contexto, o modelo pode repetir seleções ao invés de avaliar novos artigos

**Mitigações:**
- Compactação agressiva: sumarizar informação acumulada em resumos concisos preservando detalhes-chave, removendo histórico redundante
- **Regra dos 3 ciclos:** Informação com mais de 3 ciclos de processamento é automaticamente compactada ou removida do contexto ativo
- Métricas de novidade: antes de cada ciclo editorial, calcular % de conteúdo novo vs. reciclado no contexto

### 3.3 Context Confusion (Confusão de Contexto)

**Definição:** Informação irrelevante ou supérflua sobrecarrega o modelo, causando má interpretação do prompt e resultados menos relevantes, mesmo sem contradições explícitas ([Weaviate](https://weaviate.io/blog/context-engineering), [Firecrawl](https://www.firecrawl.dev/blog/context-engineering)).

**Exemplos críticos no brasileira.news:**
- Dois `curator_config.py` incompatíveis coexistindo no codebase (Bug #C-01 da auditoria): qual configuração o agente deve seguir?
- 46+ ferramentas potenciais para o pipeline de imagens (5 tiers × múltiplas APIs) — sem RAG sobre ferramentas, o modelo pode escolher o tier errado
- System prompts em `roteador_ia.py` com instruções sobre categorização misturadas com instruções sobre formatação HTML misturadas com instruções sobre SEO

**Mitigações:**

| Causa | Solução |
|---|---|
| Muitas ferramentas | RAG sobre descrições; max 15-20 por passo; segmentar por fase |
| Configs duplicadas | Single source of truth: um `editorial_config.yaml` versionado |
| Prompts sobrecarregados | Decompor em seções com XML tags: `<classificacao>`, `<formatacao>`, `<seo>` |
| Logs de debug no contexto | Nunca expor logs de debug ao LLM; isolá-los em campos não-visíveis do estado |

### 3.4 Context Clash (Conflito de Contexto)

**Definição:** Informações contraditórias dentro do contexto criam conflitos internos, confundindo o modelo e produzindo outputs incoerentes ou inconsistentes ([Weaviate](https://weaviate.io/blog/context-engineering), [Kubiya](https://www.kubiya.ai/blog/context-engineering-best-practices)).

**Exemplos graves no brasileira.news:**
- `roteador_ia.py` define 6 tiers com provedores específicos; `llm_router.py` define tiers diferentes com configuração própria — dois sistemas de roteamento independentes que podem dar instruções conflitantes
- `config_geral.py` define `WP_APP_PASSWORD` com um valor; `motor_avancado.py` define outro — qual é o correto?
- Prompts editoriais em `motor_consolidado.py` pedem "tom jornalístico neutro" enquanto `motor_rss_v2.py` não especifica tom — artigos da mesma homepage com tons inconsistentes

**Mitigações:**
- **Poda e offloading:** Remover informação desatualizada quando novos dados chegam; usar workspaces separados para informações potencialmente conflitantes
- **Single source of truth:** Uma única definição de configuração, importada por todos os módulos
- **Versionamento de prompts:** Cada prompt editorial tem versão; conflitos são detectados em CI/CD antes de deploy
- **Prioridade explícita:** Quando conflito inevitável (ex: diretriz editorial vs. dado de fonte), estabelecer hierarquia clara no system prompt:

```xml
<regras_prioridade>
1. Políticas editoriais do Diretor de Redação (prioridade máxima)
2. Guidelines de categoria do Editor responsável
3. Dados factuais verificados de fontes primárias
4. Inferências e classificações automáticas (prioridade mínima)
</regras_prioridade>
```

---

## 4. System Instructions: Projetando Prompts como Especificações

### 4.1 Estrutura de System Prompts

System prompts devem ser tratados como **especificações, não como prosa** ([Firecrawl](https://www.firecrawl.dev/blog/context-engineering)). A [Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) recomenda linguagem "extremamente clara e simples, direta" na "altitude certa" — específica o suficiente para guiar comportamento efetivamente, flexível o suficiente para fornecer heurísticas robustas.

**Template de system prompt para agentes do brasileira.news:**

```xml
<objetivo>
[Uma frase clara sobre o que o agente deve realizar]
</objetivo>

<restricoes>
- [Limites rígidos: orçamento de tokens, tempo máximo, categorias permitidas]
- [Ações proibidas: nunca publicar sem revisão, nunca expor credenciais]
- [Requisitos de estilo: tom jornalístico, português brasileiro formal]
</restricoes>

<ferramentas_disponiveis>
- [Lista concisa com descrição de 1 linha cada]
</ferramentas_disponiveis>

<contrato_de_output>
{
  "formato": "JSON",
  "campos_obrigatorios": ["titulo", "categoria", "confianca"],
  "campos_opcionais": ["tags", "subcategoria"],
  "limites": {"titulo_max_chars": 120, "confianca_min": 0.7}
}
</contrato_de_output>

<exemplos>
[2-3 exemplos canônicos e diversos, não uma lista exaustiva de edge cases]
</exemplos>
```

### 4.2 Cinco Estilos de Instrução

Pesquisa sobre arquivos AGENTS.md em produção identificou cinco estilos de instrução, com melhor eficácia quando combinados ([Firecrawl](https://www.firecrawl.dev/blog/context-engineering)):

| Estilo | Descrição | Exemplo para brasileira.news |
|---|---|---|
| **Descritivo** | Documenta convenções existentes | "Este portal usa a taxonomia tagDiv Newspaper com 16 macrocategorias e blog_id=7." |
| **Prescritivo** | Imperativos diretos sobre como agir | "Classifique cada artigo em exatamente uma macrocategoria e pelo menos uma subcategoria." |
| **Proibitivo** | Indica explicitamente o que NÃO fazer | "Nunca publique artigos sem imagem de destaque. Nunca use imagens de placeholder do Flickr." |
| **Explicativo** | Regras com justificativa | "Use Tom Jornalístico Nível 3 para artigos de Política porque nosso público espera neutralidade factual." |
| **Condicional** | Ações para situações específicas | "Se a fonte é TIER1 (G1, Folha, UOL), use o Motor Consolidado para síntese multi-fonte. Se é RSS puro, use Motor RSS." |

**Recomendação:** Combinar os cinco estilos, priorizando **proibitivo** para estabelecer limites e **condicional** para lógica situacional.

### 4.3 Contratos JSON para Outputs Estruturados

Definir schemas upfront previne que o modelo improvise nomes de campos ou formatos que quebram código downstream ([Firecrawl](https://www.firecrawl.dev/blog/context-engineering)).

```json
{
  "$schema": "artigo_processado_v1",
  "titulo": { "type": "string", "maxLength": 120 },
  "slug": { "type": "string", "pattern": "^[a-z0-9-]+$" },
  "categoria_id": { "type": "integer", "enum": [2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17] },
  "subcategoria_id": { "type": "integer" },
  "conteudo_html": { "type": "string" },
  "resumo": { "type": "string", "maxLength": 300 },
  "imagem_destaque": { "type": "string", "format": "uri" },
  "tags": { "type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 8 },
  "fonte_primaria": { "type": "string" },
  "confianca_classificacao": { "type": "number", "minimum": 0, "maximum": 1 },
  "tier_llm_usado": { "type": "integer", "minimum": 1, "maximum": 6 }
}
```

Isso substitui o sistema atual onde cada motor define seu próprio formato de saída, criando inconsistências que o curador de homepage precisa normalizar.

---

## 5. Gerenciamento de Memória

### 5.1 Arquitetura de Memória em Três Camadas

Baseado nas melhores práticas de [Weaviate](https://weaviate.io/blog/context-engineering), [Elastic](https://www.elastic.co/search-labs/blog/context-engineering-llm-evolution-agentic-ai) e [LangChain](https://blog.langchain.com/context-engineering-for-agents/):

```
┌────────────────────────────────────────────────────────────────┐
│  CAMADA 1: MEMÓRIA DE CURTO PRAZO (Context Window)             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ System prompt + mensagens recentes + tool results ativos │  │
│  │ TTL: duração do ciclo (30min - 2h)                       │  │
│  │ Limite: conforme modelo (32K-200K tokens)                │  │
│  │ Compactação automática a 85% de capacidade               │  │
│  └──────────────────────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────────────┤
│  CAMADA 2: MEMÓRIA DE TRABALHO (Redis)                         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Scratchpads dos agentes + estado do ciclo + quotas       │  │
│  │ Cache semântico de classificações recentes               │  │
│  │ Fila de publicação + circuit breaker state               │  │
│  │ TTL: 1h - 24h conforme tipo                              │  │
│  └──────────────────────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────────────┤
│  CAMADA 3: MEMÓRIA DE LONGO PRAZO (PostgreSQL + pgvector)      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Knowledge base editorial (artigos, fontes, categorias)   │  │
│  │ Memórias episódicas (decisões editoriais históricas)     │  │
│  │ Perfis de fonte (confiabilidade, frequência, viés)       │  │
│  │ Métricas de performance (por agente, fonte, categoria)   │  │
│  │ TTL: 7-365 dias conforme tipo, com manutenção periódica  │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

### 5.2 Critérios de Promoção e Expiração

Nem toda informação merece ser persistida. Permitir que o agente "reflita" sobre um evento e atribua score de importância antes de salvar ([Weaviate](https://weaviate.io/blog/context-engineering)):

```python
async def decidir_persistencia(evento: dict) -> str:
    """Decide se e onde persistir um evento."""
    score = await llm.avaliar_importancia(
        evento=evento,
        instrucao="Avalie de 0 a 1 se este evento é útil para decisões editoriais futuras."
    )
    
    if score >= 0.8:
        return "longo_prazo"   # PostgreSQL + pgvector
    elif score >= 0.5:
        return "trabalho"      # Redis com TTL de 24h
    elif score >= 0.3:
        return "curto_prazo"   # Manter no ciclo atual, depois descartar
    else:
        return "descartar"     # Não persistir
```

### 5.3 Manutenção de Memória

Memória sem manutenção se degrada — entradas antigas, de baixa qualidade ou ruidosas contaminam o contexto ([Weaviate](https://weaviate.io/blog/context-engineering)).

**Rotina de manutenção (semanal):**

| Operação | Critério | Ação |
|---|---|---|
| **Poda por recência** | Memórias episódicas >90 dias sem acesso | Arquivar ou excluir |
| **Merge de duplicatas** | Embeddings com similaridade >0.95 | Mesclar em uma entrada |
| **Atualização de fatos** | Fontes que mudaram URL, nome ou categoria | Atualizar registro |
| **Compactação de transcrições** | Logs de decisão >5.000 tokens | Sumarizar para <500 tokens |
| **Reindexação** | Após >10% de mudanças no corpus | Recalcular embeddings |

---

## 6. RAG (Retrieval-Augmented Generation) no Contexto Editorial

### 6.1 Pipeline de Recuperação

O RAG do brasileira.news deve operar em três dimensões:

```
                    Consulta do Agente
                           │
           ┌───────────────┼───────────────┐
           │               │               │
     ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
     │ Semântica  │  │  Lexical   │  │ Estrutural │
     │ (pgvector) │  │ (BM25/FTS)│  │ (SQL/meta) │
     │            │  │            │  │            │
     │ "artigos   │  │ "artigos   │  │ "artigos   │
     │  parecidos │  │  com estas │  │  desta     │
     │  no tema"  │  │  palavras" │  │  fonte/    │
     │            │  │            │  │  categoria"│
     └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
           │               │               │
           └───────────────┼───────────────┘
                           │
                    ┌──────▼──────┐
                    │  Re-ranking  │
                    │  (cross-     │
                    │  encoder ou  │
                    │  LLM leve)   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Top-K para  │
                    │  janela de   │
                    │  contexto    │
                    └─────────────┘
```

### 6.2 Anti-Padrões de RAG a Evitar

Baseado nos problemas identificados na auditoria e nas melhores práticas da indústria:

| Anti-padrão | Problema | Solução |
|---|---|---|
| **Dump completo** | Carregar todo o `catalogo_fontes.py` (398 fontes) no contexto | Indexar cada fonte; recuperar apenas as 5-10 relevantes por query |
| **Chunk cego** | Dividir artigos em chunks fixos ignorando parágrafos | Usar chunking semântico por parágrafo com overlap |
| **Recuperação sem re-ranking** | Top-K por embedding puro pode trazer ruído | Sempre re-ranquear com cross-encoder ou LLM leve |
| **Cache sem invalidação** | Cache semântico que nunca expira | TTL de 4h para classificações; invalidar quando fonte atualiza |
| **Embedding estático** | Modelo de embedding nunca atualizado | Avaliar qualidade de retrieval mensalmente; considerar fine-tuning |

### 6.3 RAG para Seleção de Ferramentas

Para evitar context confusion com muitas ferramentas disponíveis:

```python
# Registry de ferramentas com embeddings
FERRAMENTA_REGISTRY = {
    "buscar_imagem_html": {
        "descricao": "Extrai imagem do artigo original via parsing HTML",
        "embedding": embed("extrair imagem da página HTML do artigo fonte"),
        "agentes_permitidos": ["editor_fotografia", "assistente_fotografia"],
        "fase": "enriquecimento"
    },
    "buscar_imagem_flickr": {
        "descricao": "Busca imagem no Flickr Commons por palavras-chave",
        "embedding": embed("buscar foto creative commons flickr"),
        "agentes_permitidos": ["assistente_fotografia"],
        "fase": "enriquecimento"
    },
    # ...
}

async def selecionar_ferramentas(agente: str, tarefa: str, max_tools: int = 15):
    """Seleciona ferramentas relevantes via RAG."""
    embedding_tarefa = await gerar_embedding(tarefa)
    ferramentas_agente = [
        f for f in FERRAMENTA_REGISTRY.values()
        if agente in f["agentes_permitidos"]
    ]
    # Ranquear por similaridade semântica
    scored = [(f, cosine_sim(embedding_tarefa, f["embedding"])) 
              for f in ferramentas_agente]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [f[0] for f in scored[:max_tools]]
```

---

## 7. Ferramentas e Respostas

### 7.1 Design de Ferramentas Token-Eficientes

Ferramentas devem ser **token-eficientes, autocontidas, robustas a erro e extremamente claras** em relação ao uso pretendido ([Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)).

**Princípios para o brasileira.news:**

1. **Retornar o mínimo necessário:** Uma ferramenta de scraping não retorna o HTML completo — retorna título, lide, conteúdo limpo e metadados
2. **Parâmetros descritivos e unívocos:** `fonte_url` em vez de `url`; `categoria_id` em vez de `cat`
3. **Mensagens de erro acionáveis:** Não apenas "Erro 429" mas "Rate limit atingido no Google CSE. Próxima tentativa em 47s. Quota restante: 23/100."
4. **Promover eficiência:** Se a ferramenta pode resolver em uma chamada, não forçar duas

**Template de ferramenta:**

```python
@tool(
    name="classificar_artigo",
    description="""Classifica artigo em macrocategoria (1 de 16) e subcategoria.
    Retorna: categoria_id, subcategoria_id, confianca (0-1).
    Usar quando: novo artigo ingerido precisa de classificação editorial.
    NÃO usar para: reclassificação de artigos já publicados (usar reclassificar_artigo)."""
)
async def classificar_artigo(
    titulo: str,  # Título do artigo (max 200 chars)
    lide: str,    # Primeiro parágrafo / lead (max 500 chars)
    fonte: str    # Nome da fonte (ex: "G1", "Folha de S.Paulo")
) -> dict:
    """Retorna classificação com confiança."""
    # Implementação...
    return {
        "categoria_id": 2,        # Política
        "subcategoria_id": 201,   # Congresso
        "confianca": 0.91,
        "justificativa_breve": "Artigo sobre votação no Senado"
    }
```

### 7.2 Tratamento de Respostas de Ferramentas

Resultados de ferramentas são uma das maiores fontes de inflação de contexto. Diretrizes:

| Cenário | Ação |
|---|---|
| Resultado processado com sucesso | Manter derivação, limpar resultado bruto após 3 mensagens |
| Erro transitório (timeout, 429) | Manter no ciclo para retry; podar após resolução |
| Erro persistente (fonte offline) | Escalar para nível superior; registrar em memória episódica |
| Resultado muito grande (>2K tokens) | Sumarizar antes de inserir no contexto; armazenar original em working memory |

---

## 8. Estado Global e Coordenação

### 8.1 O Problema do Estado Compartilhado

No sistema atual, a falta de coordenação entre motores é uma das 3 causas-raiz sistêmicas identificadas na auditoria: deduplicação check-then-act entre Raias 1/2 produz duplicatas; curadoria clear→apply deixa homepage vazia por 30-90 segundos; três motores rodam via cron sem coordenação.

### 8.2 Padrão de Estado Global no LangGraph

```python
class EstadoGlobal(TypedDict):
    """Estado compartilhado entre todos os agentes via LangGraph checkpointing."""
    
    # Controle de ciclo
    ciclo_atual: str                    # ID do ciclo ativo
    fase_atual: str                     # "ingestao" | "processamento" | "publicacao" | "curadoria"
    
    # Locks distribuídos (via Redis)
    artigos_em_processamento: set[str]  # URLs sendo processadas (evita duplicata)
    posicoes_homepage_locked: set[int]  # Posições sendo atualizadas (evita vazio)
    
    # Quotas e limites
    quota_llm: dict[str, int]           # {provedor: chamadas_restantes}
    quota_imagem: dict[str, int]        # {api: buscas_restantes}
    
    # Métricas do ciclo
    artigos_ingeridos: int
    artigos_publicados: int
    erros_contabilizados: int
    custo_estimado_usd: float
```

### 8.3 Transição Atômica da Homepage

Resolver o bug de homepage vazia (30-90s sem conteúdo) requer **aplicação atômica** das tags — todas de uma vez, não clear→apply sequencial:

```python
async def atualizar_homepage_atomico(novas_posicoes: dict[int, int]):
    """Atualiza homepage de forma atômica: prepare → swap → cleanup."""
    
    # 1. PREPARE: Aplicar tags novas sem remover antigas
    for posicao, post_id in novas_posicoes.items():
        tag = f"home-posicao-{posicao}-nova"
        await wp_api.adicionar_tag(post_id, tag)
    
    # 2. SWAP: Trocar tags em uma transação
    async with db.transaction():
        for posicao in range(1, 15):
            tag_antiga = f"home-posicao-{posicao}"
            tag_nova = f"home-posicao-{posicao}-nova"
            # Remover antiga e renomear nova em uma operação
            await wp_api.swap_tags(tag_antiga, tag_nova)
    
    # 3. CLEANUP: Remover tags temporárias
    await wp_api.limpar_tags_temporarias()
```

---

## 9. Métricas de Qualidade de Contexto

Para monitorar a saúde do context engineering em produção, implementar as seguintes métricas ([Firecrawl](https://www.firecrawl.dev/blog/context-engineering)):

### 9.1 Métricas Primárias

| Métrica | Descrição | Meta | Alerta |
|---|---|---|---|
| **Taxa de sucesso por tarefa** | % de artigos processados com sucesso end-to-end | >95% | <90% |
| **Taxa de alucinação** | % de outputs com contradição detectada vs. fonte | <2% | >5% |
| **Utilização de contexto** | % de tokens que efetivamente influenciam o output | >60% | <40% |
| **Latência vs. sucesso** | Tempo médio por artigo vs. qualidade | <45s/art, score >0.8 | >90s ou score <0.6 |
| **Frescor do contexto** | Idade média da informação na janela | <4h | >12h |

### 9.2 Métricas de Custo

| Métrica | Cálculo | Otimização |
|---|---|---|
| **Tokens por artigo** | Total de tokens consumidos / artigos publicados | Comprimir e podar para reduzir |
| **Custo por artigo** | Custo total LLM / artigos publicados | Target: <$0.02/artigo para atingir 1.000/dia em ~$20/dia |
| **Ratio compactação** | Tokens pré-compactação / pós-compactação | Meta: 5:1 ou melhor |
| **Cache hit rate** | Classificações/embeddings servidas de cache | Meta: >70% |

### 9.3 Dashboard de Observabilidade

Integrar com LangSmith ou similar para rastrear:
- Token usage por agente e por passo
- Latência de cada ferramenta
- Frequência de compactação e trimming
- Taxas de fallback entre tiers LLM
- Drift de qualidade ao longo do tempo

---

## 10. Aplicação à Arquitetura Proposta

### 10.1 Mapeamento de Estratégias por Agente

| Agente | Write | Select | Compress | Isolate |
|---|---|---|---|---|
| **Diretor de Redação** | Plano editorial → Redis | Métricas macro via query | Resumo diário de ciclos | Janela própria, ~8K tokens |
| **Editor-Chefe** | Distribuição de pautas → Redis | Plano do Diretor + candidatos | Handoffs sumarizados | Janela própria, ~16K tokens |
| **Pauteiro** | Radar de fontes → Redis | Just-in-time por fonte | TF-IDF compactado | Isolado por ciclo de ingestão |
| **Editores de Área** | Decisões editoriais → pgvector | Artigos da sua editoria apenas | Tool result clearing | 1 janela por editoria |
| **Repórteres** | Artigo redigido → fila WP | Briefing + fontes primárias | N/A (tarefa curta) | 1 janela por matéria |
| **Editor de Fotografia** | Decisões de imagem → log | Quotas + histórico de uso | Limpar results de HTTP | Sandbox de imagens |
| **Sub-editor** | Revisão → log de qualidade | Artigo + guidelines da editoria | N/A (tarefa curta) | 1 janela por revisão |

### 10.2 Fluxo de Contexto em um Ciclo Completo

```
INÍCIO DO CICLO (T+0)
│
├── Diretor consulta memória episódica → define plano editorial
│   Write: plano_editorial → Redis
│   Select: métricas das últimas 24h via query PostgreSQL
│
├── Pauteiro recebe plano (Select) → processa fontes
│   Select: just-in-time por fonte (não carrega catálogo inteiro)
│   Write: radar com 200 artigos candidatos → Redis
│   Compress: apenas metadados (título, fonte, score), não conteúdo
│
├── Editor-Chefe seleciona 50 artigos (Select do radar)
│   Compress: handoff sumarizado para cada Editor de Área
│   Isolate: distribui por editoria
│
├── [PARALELO] Editores distribuem para Repórteres
│   Isolate: cada Repórter opera em janela independente
│   Select: 1 briefing + fontes primárias para sua matéria
│   Write: artigo redigido → fila de publicação
│
├── [PARALELO] Editor de Fotografia
│   Isolate: sandbox de imagens, retorna apenas referências
│   Select: RAG sobre ferramentas de imagem por contexto
│
├── Sub-editor revisa cada artigo
│   Isolate: 1 janela por revisão
│   Compress: tool result clearing após revisão
│
├── Publicação atômica no WordPress
│   Select: artigos da fila aprovados
│
└── Curadoria da Homepage
    Select: artigos das últimas 4h + métricas de performance
    Write: decisões de curadoria → memória episódica
    Compress: limpar contexto do ciclo anterior

FIM DO CICLO (T+30min a T+2h)
```

### 10.3 Resolução dos 329 Bugs via Context Engineering

Muitos dos bugs identificados na auditoria se resolvem naturalmente com a aplicação correta de context engineering:

| Cluster de Bugs | Quantidade | Estratégia de Resolução |
|---|---|---|
| Credenciais hardcoded (15+ locais) | ~20 bugs | **Isolate:** Variáveis de ambiente isoladas, nunca no contexto do LLM |
| Memory leaks (cloudscraper, newspaper, etc.) | ~15 bugs | **Write:** Checkpointing com liberação explícita de recursos |
| Homepage vazia 30-90s | ~5 bugs | **Isolate:** Transição atômica com estado isolado |
| Configs duplicadas/contraditórias | ~12 bugs | **Select:** Single source of truth; RAG sobre configuração |
| Acúmulo de histórico sem limpeza | ~10 bugs | **Compress:** Compactação automática + trimming por regras |
| Prompts contraditórios entre módulos | ~8 bugs | **Write:** Prompts versionados em repositório; **Select:** Carregar apenas o relevante |
| Quota CSE compartilhada entre tiers | ~4 bugs | **Isolate:** Estado de quota isolado por tier no Redis |
| Race conditions na deduplicação | ~6 bugs | **Isolate:** Locks distribuídos via Redis; estado global coordenado |

---

## 11. Checklist de Implementação

### Fase 1 — Fundação (Semanas 1-4)

- [x] Definir schema de estado global no LangGraph
- [x] Implementar camadas de memória: Redis (trabalho) + PostgreSQL/pgvector (longo prazo)
- [x] Criar template de system prompt padronizado com XML tags
- [~] Implementar contratos JSON para todos os outputs inter-agente
- [x] Migrar `historico_links.txt` para tabela indexada (via deduplicador)
- [~] Configurar single source of truth para configurações (`editorial_config.yaml`)
- [x] Eliminar todas as credenciais hardcoded (todas em .env.versao2)

### Fase 2 — Estratégias Core (Semanas 5-8)

- [~] Implementar scratchpads em Redis para cada papel de agente
- [x] Criar pipeline de recuperação híbrida (semântica + lexical via pgvector)
- [~] Implementar compactação automática a 85% da janela de contexto
- [~] Configurar tool result clearing após processamento
- [~] Implementar RAG sobre ferramentas (max 15-20 por passo)
- [~] Criar protocolos de handoff inter-agente (max 1.500 tokens)

### Fase 3 — Isolamento e Escala (Semanas 9-12)

- [x] Deploy da hierarquia multi-agente com janelas isoladas
- [~] Implementar sandbox para pipeline de imagens
- [x] Configurar transição atômica da homepage (CuradorHome 19 tags)
- [x] Implementar locks distribuídos para deduplicação (Redis-based)
- [ ] Criar rotina de manutenção de memória (semanal)
- [ ] Deploy de dashboard de observabilidade com métricas de contexto

### Fase 4 — Otimização (Semanas 13-16)

- [ ] Medir e otimizar ratio de compactação (meta: 5:1)
- [ ] Fine-tunar thresholds de promoção de memória
- [ ] Implementar validação anti-poisoning na classificação
- [ ] Otimizar estratégia de chunking baseado em métricas de retrieval
- [ ] Ajustar quotas e limites por agente baseado em uso real
- [ ] Documentar padrões emergentes e atualizar guidelines

---

## 12. Lições Aprendidas da Implementação V2

### 12.1 Roteamento Multi-Provedor como Estratégia de Contexto

A implementação V2 demonstrou que **diversificação de provedores LLM** é uma estratégia de resiliência de contexto:

| Tier | Uso | Modelos Primários | Contexto Típico |
|---|---|---|---|
| **PREMIUM** | Decisões editoriais, curadoria homepage | GPT-5.4, Claude Sonnet 4 | ~8K tokens, reasoning alto |
| **REDACAO** | Redação de artigos, revisão | GPT-4o, Claude Sonnet 4 | ~32K tokens, geração longa |
| **ECONOMICO** | Classificação, tags, triagem | GPT-4o-mini, Gemini Flash-Lite | ~4K tokens, alta velocidade |
| **MULTIMODAL** | Análise de imagens, gráficos | GPT-4o, Gemini 2.5 Flash | ~16K tokens, visual |

**Insight:** E2E test mostrou GPT-5.4 para decisões editoriais + GPT-4o para redação como split ótimo qualidade/custo (~$0.01/ciclo). Fallback Anthropic→OpenAI funcionou transparentemente via LiteLLM quando créditos Anthropic esgotaram.

### 12.2 Budget como Restrição de Contexto

Outage de 4 dias (19-23/mar) causado por limite de 2.000 chamadas/dia — insuficiente para 34 chaves e 7 provedores. Elevado para 7.500. Lesson: **budget management é uma dimensão de context engineering** — limites artificiais restringem a capacidade do sistema de preencher contextos adequadamente.

### 12.3 Tags WordPress como Interface de Contexto Visual

O sistema TDC (tagDiv Composer) do Newspaper Theme usa tags como **ponte entre contexto editorial (agentes) e contexto visual (layout)**:
- 19 posições homepage: `home-manchete`, `home-submanchete`, `home-politica`...
- 14 seções de editoria: `secao-politica-manchete`, `secao-economia-destaque`...
- Freshness decay: `score * max(0.1, 1.0 - (age_hours / 8.0))`
- Breaking news: URGENTE → position 0 em <10 min

### 12.4 Validação Estrutural como Gate de Qualidade

O Revisor V2 implementa **5 validadores estruturais** que atuam como hard gate antes da publicação — garantindo que o contexto gerado pelo LLM atenda padrões TIER 1:
1. Hierarquia de headings (H1→H2→H3, sem saltos)
2. Atribuição de fonte (link nos primeiros 300 chars)
3. Comprimento mínimo (500+ palavras para artigo completo)
4. Imagem de destaque obrigatória com caption
5. SEO (título 50-65 chars, meta description 130-160 chars)

---

## 13. Referências e Leitura Complementar

As fontes consultadas para este documento representam o estado da arte em context engineering para sistemas de IA agêntica:

- [Anthropic — Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — Guia fundamental sobre Write/Select/Compress/Isolate, context rot, e padrões de sub-agentes
- [LangChain — Context Engineering for Agents](https://blog.langchain.com/context-engineering-for-agents/) — Framework prático com integração LangGraph/LangSmith
- [Weaviate — Context Engineering: LLM Memory and Retrieval](https://weaviate.io/blog/context-engineering) — Arquitetura de memória, 6 pilares, e padrões de retrieval
- [Kubiya — Context Engineering Best Practices](https://www.kubiya.ai/blog/context-engineering-best-practices) — Estratégias Write/Select/Compress/Isolate com exemplos práticos e modos de falha
- [Firecrawl — Context Engineering vs Prompt Engineering](https://www.firecrawl.dev/blog/context-engineering) — Técnicas de produção, métricas, e estilos de instrução
- [Elastic — Context Engineering for Agentic AI](https://www.elastic.co/search-labs/blog/context-engineering-llm-evolution-agentic-ai) — Context rot, attention budget, e memória de longo prazo
- [Andrej Karpathy](https://x.com/karpathy/status/1937902205765607626) — Definição seminal de context engineering como "a arte e ciência de preencher a janela de contexto com a informação certa para o próximo passo"
- [Glean — Context Engineering vs Prompt Engineering](https://www.glean.com/perspectives/context-engineering-vs-prompt-engineering-key-differences-explained) — Comparação detalhada com analogia CPU/RAM de Karpathy
