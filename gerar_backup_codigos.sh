
#!/bin/bash

ARQUIVO_SAIDA="/home/bitnami/backup_integral_robos.txt"

echo "=== BACKUP DOS ROBOS - $(date) ===" > $ARQUIVO_SAIDA

echo "" >> $ARQUIVO_SAIDA

for arquivo in /home/bitnami/*.py /home/bitnami/*.sh; do

    if [ -f "$arquivo" ] && [[ "$arquivo" != *"/gerar_backup_codigos.sh" ]]; then

        echo "-------------------------------------------------------" >> $ARQUIVO_SAIDA

        echo " ARQUIVO: $arquivo" >> $ARQUIVO_SAIDA

        echo "-------------------------------------------------------" >> $ARQUIVO_SAIDA

        cat "$arquivo" >> $ARQUIVO_SAIDA

        echo -e "\n\n" >> $ARQUIVO_SAIDA

    fi

done

echo "[SUCESSO] Backup gerado: $ARQUIVO_SAIDA"

