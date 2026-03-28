# Prompt para Claude Code — brasileira.news V3

## Como Usar

### Passo 1 — Preparar o servidor

No terminal SSH do servidor (VS Code terminal), execute estes comandos para criar a estrutura e transferir os briefings:

```bash
# 1. Criar a pasta V3 (se ainda não existir)
mkdir -p /home/bitnami/V3/docs

# 2. Clonar o repo (se ainda não estiver clonado)
cd /home/bitnami/V3
git init
git remote add origin https://github.com/redes-dsc/brasileira.git
git fetch origin main
git checkout -b v3-implementation

# OU, se o repo já estiver clonado em /home/bitnami/:
cd /home/bitnami/V3
git init
git checkout -b v3-implementation
```

### Passo 2 — Transferir os briefings para o servidor

Copie todos os arquivos .md de briefing para `/home/bitnami/V3/docs/`. Você pode fazer isso via SCP do seu computador local, ou colando o conteúdo via terminal. São 15 arquivos:

```bash
# Via SCP do computador local (ajuste o caminho local):
scp briefing-*.md bitnami@SEU_IP:/home/bitnami/V3/docs/
scp context-engineering-brasileira-news.pplx.md bitnami@SEU_IP:/home/bitnami/V3/docs/context-engineering.md
scp catalogo_modelos_llm_2026.md bitnami@SEU_IP:/home/bitnami/V3/docs/
scp briefing-implementacao-brasileira-news-v3.pplx.md bitnami@SEU_IP:/home/bitnami/V3/docs/briefing-master.md
```

### Passo 3 — Copiar o CLAUDE.md para a raiz do projeto

```bash
# Copie o CLAUDE.md para /home/bitnami/V3/
cp CLAUDE.md /home/bitnami/V3/CLAUDE.md
```

### Passo 4 — Abrir o Claude Code

```bash
cd /home/bitnami/V3
claude
```

### Passo 5 — Colar o prompt abaixo no Claude Code

---

## PROMPT PRINCIPAL (cole este bloco inteiro no Claude Code)

```
Você é o arquiteto-chefe e desenvolvedor sênior do sistema multi-agente brasileira.news V3 — um portal jornalístico brasileiro 100% automatizado por IA que processa 1.000+ artigos/dia de 648+ fontes.

LEIA PRIMEIRO:
1. O arquivo CLAUDE.md na raiz deste diretório — contém TODAS as regras, estrutura, configurações e restrições do projeto
2. A pasta docs/ — contém 15 briefings técnicos detalhados (1.500-4.800 linhas cada) com código de produção, schemas, testes e diagramas

SEU MANDATO:
Implementar o sistema V3 completo, componente por componente, seguindo RIGOROSAMENTE a ordem de prioridade definida no CLAUDE.md e os briefings individuais na pasta docs/.

COMO TRABALHAR:
1. Comece lendo CLAUDE.md por completo
2. Para cada componente, leia o briefing correspondente em docs/ ANTES de escrever qualquer código
3. Implemente na ORDEM EXATA listada no CLAUDE.md (shared → smart_router → worker_pool → classificador → reporter → fotografo → revisor → consolidador → curador_homepage → pauteiro → editor_chefe → monitor_concorrencia → monitor_sistema)
4. Cada briefing contém: diagnóstico V2, arquitetura V3, código de produção, schemas Kafka/SQL, testes e checklist
5. Após implementar cada componente, rode os testes definidos no briefing
6. Faça commits atômicos por componente: feat(smart_router): implement SmartLLMRouter V3

INFRAESTRUTURA (implementar primeiro, antes dos componentes):
- docker-compose.infra.yml com: Kafka (KRaft, sem Zookeeper), Redis 7, PostgreSQL 16 + pgvector
- docker-compose.yml que orquestra todos os 12 componentes
- .env.example com TODAS as variáveis de ambiente
- migrations/ com DDL completo (tabelas, índices, extensões pgvector)
- shared/ com os módulos reutilizáveis (config, kafka_client, redis_client, db, wp_client, memory, schemas)

REGRAS INVIOLÁVEIS (violação = bug crítico):
- Reporter publica direto (status="publish"), NUNCA draft
- Revisor corrige in-place, NUNCA rejeita
- Homepage scoring = tier PREMIUM (NUNCA econômico)
- Image query generation = tier PREMIUM
- Pauteiro NÃO é entry point do conteúdo
- Editor-Chefe NÃO é gatekeeper (está no FIM, não no início)
- Consolidador aceita 1 fonte (reescreve), não exige MIN_SOURCES=3
- Focas NUNCA desativa fontes
- Ingestão paralela — um erro NUNCA trava outras fontes
- Token budgets são alertas, NUNCA bloqueiam operação
- Todos os agentes têm memória em 3 camadas (pgvector + PostgreSQL + Redis)

COMECE AGORA:
Leia CLAUDE.md, depois leia docs/briefing-master.md para contexto geral, e então implemente shared/ (o módulo de código compartilhado). Após shared/ estar completo com testes, prossiga para smart_router/ seguindo docs/briefing-smart-llm-router-v3.md.

Para cada componente, entregue:
- Código de produção completo (não stubs)
- Dockerfile
- Testes (pytest, mínimo 80% cobertura)
- Commit com mensagem descritiva

Trabalhe até completar todos os 13 itens (shared + 12 componentes).
```

---

## PROMPT ALTERNATIVO — Se o Claude Code tiver limite de contexto

Se o Claude Code não conseguir processar todos os briefings de uma vez (2.2 MB de documentação), use esta abordagem incremental:

```
Leia CLAUDE.md e docs/briefing-master.md. Depois implemente APENAS:
1. shared/ (módulos compartilhados)
2. smart_router/ (leia docs/briefing-smart-llm-router-v3.md)
3. worker_pool/ (leia docs/briefing-worker-pool-coletores-v3.md)

Siga RIGOROSAMENTE o CLAUDE.md para regras e estrutura.
Faça commits atômicos por componente.
Rode os testes de cada briefing antes de prosseguir.
```

Após completar esses 3, cole o próximo bloco:

```
Prossiga com a implementação. Leia e implemente:
4. classificador/ (leia docs/briefing-classificador-kafka-v3.md)
5. reporter/ (leia docs/briefing-reporter-v3.md)
6. fotografo/ (leia docs/briefing-fotografo-v3.md)

Mantenha a mesma estrutura, padrões e regras do CLAUDE.md.
```

E depois:

```
Prossiga com:
7. revisor/ (leia docs/briefing-revisor-v3.md)
8. consolidador/ (leia docs/briefing-consolidador-v3.md)
9. curador_homepage/ (leia docs/briefing-curador-homepage-v3.md)
```

E por fim:

```
Finalize com:
10. pauteiro/ (leia docs/briefing-pauteiro-v3.md)
11. editor_chefe/ (leia docs/briefing-editor-chefe-v3.md)
12. monitor_concorrencia/ (leia docs/briefing-monitor-concorrencia-v3.md)
13. monitor_sistema/ (leia docs/briefing-monitor-focas-v3.md)

Após todos os componentes, crie:
- docker-compose.yml final orquestrando todos os serviços
- README.md com instruções de deploy
- Script deploy.sh para setup inicial
```

---

## Validação Pós-Implementação

Após o Claude Code completar, rode estes comandos no terminal:

```bash
# 1. Verificar estrutura
find /home/bitnami/V3 -name "*.py" | wc -l  # deve ser 50+
find /home/bitnami/V3 -name "test_*.py" | wc -l  # deve ser 12+

# 2. Verificar regras invioláveis
echo "=== Verificando violações ==="
# Não pode existir status="draft" em nenhum publisher
grep -r "status.*draft" /home/bitnami/V3 --include="*.py" && echo "❌ VIOLAÇÃO: draft encontrado" || echo "✅ Sem drafts"

# Não pode existir MIN_SOURCES=3
grep -r "MIN_SOURCES.*3\|min_sources.*3" /home/bitnami/V3 --include="*.py" && echo "❌ VIOLAÇÃO: MIN_SOURCES=3" || echo "✅ Sem MIN_SOURCES=3"

# Não pode existir REJECT no Revisor
grep -r "REJECT\|reject" /home/bitnami/V3/revisor --include="*.py" && echo "❌ VIOLAÇÃO: REJECT no revisor" || echo "✅ Sem REJECT"

# Não pode desativar fontes no Focas
grep -r "is_active.*False\|desativar\|deactivate" /home/bitnami/V3/monitor_sistema --include="*.py" && echo "❌ VIOLAÇÃO: desativação de fontes" || echo "✅ Sem desativação"

# Homepage e Imagem devem usar PREMIUM
grep -r "ECONOMICO\|economico\|ECONÔMICO" /home/bitnami/V3/curador_homepage --include="*.py" && echo "❌ VIOLAÇÃO: econômico na homepage" || echo "✅ Homepage sem econômico"
grep -r "ECONOMICO\|economico\|ECONÔMICO" /home/bitnami/V3/fotografo/query_generator.py && echo "❌ VIOLAÇÃO: econômico em imagem" || echo "✅ Imagem sem econômico"

# 3. Rodar testes
cd /home/bitnami/V3
source ../venv/bin/activate
pip install -r requirements-base.txt
pytest tests/ -v --tb=short

# 4. Build dos containers
docker compose -f docker-compose.infra.yml build
docker compose build

# 5. Subir infraestrutura
docker compose -f docker-compose.infra.yml up -d
sleep 10

# 6. Rodar migrações
psql -h localhost -U brasileira -d brasileira_v3 -f migrations/001_schema_base.sql
psql -h localhost -U brasileira -d brasileira_v3 -f migrations/002_pgvector.sql
psql -h localhost -U brasileira -d brasileira_v3 -f migrations/003_indices.sql

# 7. Subir todos os serviços
docker compose up -d

# 8. Health check
docker compose ps
docker compose logs --tail=20
```
