
#!/bin/bash

WP_CONFIG="/opt/bitnami/wordpress/wp-config.php"



# Verifica se os limites ja existem para nao duplicar

if ! grep -q "WP_MEMORY_LIMIT" "$WP_CONFIG"; then

    # Injeta os comandos logo apos a definicao de debug

    sed -i "/define( 'WP_DEBUG', false );/a define( 'WP_MEMORY_LIMIT', '1024M' );\ndefine( 'WP_MAX_MEMORY_LIMIT', '2048M' );" "$WP_CONFIG"

    echo "[OK] Memoria RAM do WordPress aumentada para 2GB!"

else

    echo "[INFO] Os limites de memoria ja estao configurados no wp-config."

fi



# Aumenta tambem o tempo limite de processamento do PHP

PHP_INI="/opt/bitnami/php/etc/php.ini"

sudo sed -i 's/max_execution_time = .*/max_execution_time = 300/' "$PHP_INI"

sudo sed -i 's/memory_limit = .*/memory_limit = 1024M/' "$PHP_INI"

echo "[OK] Tempo de execucao do PHP aumentado!"



# Reinicia tudo para assumir as mudancas

sudo /opt/bitnami/ctlscript.sh restart

