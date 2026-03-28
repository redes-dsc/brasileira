#!/bin/bash
# Deploy do Home Curator Agent — brasileira.news
# Cria tabela de log e configura cron.

set -e

CURATOR_DIR="/home/bitnami/curator"
VENV_PYTHON="/home/bitnami/venv/bin/python3"
LOG_DIR="/home/bitnami/logs"

echo "═══════════════════════════════════════════════════════"
echo "  DEPLOY — Home Curator Agent"
echo "═══════════════════════════════════════════════════════"

# 1. Verificar Python e dependências
echo ""
echo "[1/4] Verificando dependências..."
$VENV_PYTHON -c "import pymysql; import requests; import dotenv; print('✓ Dependências OK')"

# 2. Criar tabela de log
echo ""
echo "[2/4] Criando tabela de log..."
$VENV_PYTHON -c "
import sys
sys.path.insert(0, '$CURATOR_DIR')
from curator_agent import create_log_table
create_log_table()
print('✓ Tabela wp_7_curator_log criada/verificada')
" || true

# 3. Criar diretório de logs
echo ""
echo "[3/4] Verificando diretório de logs..."
mkdir -p "$LOG_DIR"
echo "✓ $LOG_DIR existe"

# 4. Configurar cron
echo ""
echo "[4/4] Configurando cron..."

CRON_LINE="15,45 * * * * $VENV_PYTHON $CURATOR_DIR/curator_agent.py >> $LOG_DIR/curator_cron.log 2>&1"

# Verificar se já existe
if crontab -l 2>/dev/null | grep -q "curator_agent.py"; then
    echo "⚠ Entrada cron já existe. Atualizando..."
    # Remove a linha antiga e adiciona nova
    (crontab -l 2>/dev/null | grep -v "curator_agent.py"; echo "$CRON_LINE") | crontab -
else
    # Adicionar nova entrada
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
fi

echo "✓ Cron configurado: minutos 15 e 45 (intercalado com motor_rss)"
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  DEPLOY CONCLUÍDO!"
echo ""
echo "  Cron ativo: $CRON_LINE"
echo ""
echo "  Logs em: $LOG_DIR/curator_YYYY-MM-DD.log"
echo "  Cron log: $LOG_DIR/curator_cron.log"
echo ""
echo "  Para testar manualmente:"
echo "    CURATOR_DRY_RUN=1 $VENV_PYTHON $CURATOR_DIR/curator_agent.py"
echo "═══════════════════════════════════════════════════════"
