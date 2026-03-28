#!/bin/bash
cd /home/bitnami

echo "=== INICIANDO RAIA 2 (SCRAPERS NATIVOS): $(date) ==="

for gaveta in gov_ministerios reguladores estados judiciario_conselhos grandes_portais entretenimento_fofoca internacional infra_energia meio_ambiente_esg esportes tecnologia_ia; do
    echo "-> Acionando Gaveta: $gaveta"
    /usr/bin/python3 /home/bitnami/motor_scrapers.py $gaveta
    sleep 5
done

echo "=== RAIA 2 FINALIZADA: $(date) ==="
