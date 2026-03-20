#!/bin/bash
# Entrar forçosamente na pasta correta
cd /home/bitnami

echo "=== Iniciando a coleta de dados - Motor Mestre: $(date) ==="

echo "[1/3] Executando: Parte 1 - Estrutura e Executivo..."
/usr/bin/python3 /home/bitnami/motor_mestre.py ministerios_autarquias

echo "[2/3] Executando: Parte 2 - Justica e Conselhos..."
/usr/bin/python3 /home/bitnami/motor_mestre.py justica_conselhos

echo "[3/3] Executando: Parte 3 - Estados e Internacional..."
/usr/bin/python3 /home/bitnami/motor_mestre.py estados_internacional

echo "=== Processo finalizado com sucesso! ==="
