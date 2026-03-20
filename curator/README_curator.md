# Home Curator Agent — Editor de Primeira Página

Agente autônomo de curadoria editorial para a homepage da **brasileira.news**.

## O que faz

A cada 30 minutos, o agente:
1. **Busca** posts publicados nas últimas 4 horas (configurável)
2. **Pontua** cada post com critérios objetivos + avaliação LLM (Gemini Flash)
3. **Decide** a manchete principal via LLM Premium (Claude → GPT-4o → Gemini Pro)
4. **Distribui** os melhores posts nas 14 posições de destaque da homepage via TAGs
5. **Loga** cada ciclo no banco de dados

**Nenhum conteúdo é modificado** — apenas tags são adicionadas/removidas.

## Arquitetura

```
curator/
├── curator_agent.py        # Orquestrador principal
├── curator_scorer.py       # Scoring (objetivo + LLM)
├── curator_tagger.py       # Gerenciamento de tags via WP REST API
├── curator_config.py       # Configuração e pesos
├── deploy_curator.sh       # Deploy e cron
├── criar_tags_editoriais.py    # Criação das tags (executar 1x)
├── seed_tags_iniciais.py       # Seed inicial de posts
├── migrar_homepage_tags.py     # Migração do tdc_content
└── aplicar_homepage_tags.py    # Aplicação do tdc_content ao DB
```

## TAGs Editoriais

| TAG | Posição na Home | Posts |
|---|---|---|
| `home-manchete` | Manchete principal | 1 |
| `home-submanchete` | Submanchetes | 3 |
| `home-politica` | Destaque Política | 1 |
| `home-economia` | Destaque Economia | 2 |
| `home-tecnologia` | Grade Tecnologia | 8 |
| `home-entretenimento` | Grade Entretenimento | 5 |
| `home-ciencia` | Grade Ciência | 5 |
| `home-internacional` | Grid Internacional | 5 |
| `home-saude` | Grid Saúde | 5 |
| `home-meioambiente` | Destaque Meio Ambiente | 4 |
| `home-bemestar` | Destaque Bem-Estar | 2 |
| `home-infraestrutura` | Destaque Infraestrutura | 5 |
| `home-cultura` | Destaque Cultura | 5 |
| `home-sociedade` | Destaque Sociedade | 3 |

## Scoring

### Critérios Objetivos (0 a ~85 pts)

| Critério | Pontos |
|---|---|
| Fonte oficial (gov.br, jus.br) | +30 |
| Matéria consolidada | +20 |
| Tema de alto interesse | +15 |
| Publicado há < 1h | +10 |
| Com imagem de destaque | +10 |
| Título SEO (50-80 chars) | +5 |
| Excerpt preenchido | +5 |
| ≥ 3 tags relevantes | +5 |
| Internacional sem BR | -20 |
| Tema de nicho | -15 |
| Conteúdo curto (< 300 palavras) | -10 |
| Sem imagem | -10 |
| Título curto (< 30 chars) | -5 |

### Avaliação LLM (0 a 50 pts)
- **Gemini 2.0 Flash** avalia título + excerpt
- Máximo 50 chamadas por ciclo
- Timeout: 20s, fallback: 25 pts

### Decisão de Manchete
- **Claude Sonnet 4** → GPT-4o → Gemini 2.5 Pro (cascata)
- Compara os 5 melhores candidatos
- 1 chamada por ciclo

## Variáveis de Ambiente

| Variável | Default | Descrição |
|---|---|---|
| `CURATOR_WINDOW_HOURS` | 4 | Janela de busca em horas |
| `CURATOR_DRY_RUN` | 0 | 1 = simula sem aplicar tags |

## Uso

```bash
# Dry-run (simula sem aplicar)
CURATOR_DRY_RUN=1 /home/bitnami/venv/bin/python3 curator_agent.py

# Ciclo completo
/home/bitnami/venv/bin/python3 curator_agent.py

# Deploy + cron
bash deploy_curator.sh
```

## Cron

Roda nos minutos **15 e 45** de cada hora, intercalado com o motor_rss (minutos 0 e 30).

```
15,45 * * * * /home/bitnami/venv/bin/python3 /home/bitnami/curator/curator_agent.py
```

## Logs

- **Arquivo diário**: `/home/bitnami/logs/curator_YYYY-MM-DD.log`
- **Cron log**: `/home/bitnami/logs/curator_cron.log`
- **Banco**: tabela `wp_7_curator_log` com ciclo, post_id, posição e scores
