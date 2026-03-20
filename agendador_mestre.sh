
#!/bin/bash

# Entrar forcosamente na pasta correta

cd /home/bitnami



echo "=== INICIANDO RAIA 1 (MOTOR MESTRE RSS): $(date) ==="



# Varrer todas as chaves exatas que existem no catalogo_fontes.py

for gaveta in agencia_brasil gov_central ministerios_autarquias legislativo judiciario_controle estados_br meio_ambiente_br meio_ambiente_intl esg_sustentabilidade infra_telecom_logistica tecnologia_br tecnologia_intl ia_ciencia ciberseguranca grandes_portais_br nativos_br economia_financas entretenimento_br entretenimento_intl esportes_br esportes_intl internacional_pt internacional_global; do

    echo "---------------------------------------------------"

    echo "[*] Acionando Gaveta: $gaveta"

    echo "---------------------------------------------------"

    /usr/bin/python3 /home/bitnami/motor_mestre.py $gaveta

    sleep 3

done



echo "=== MOTOR MESTRE FINALIZADO COM SUCESSO: $(date) ==="

