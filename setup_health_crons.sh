#!/bin/bash
CRON_JOB="0 3 * * * /home/bitnami/venv/bin/python3 /home/bitnami/motor_rss/auto_health_raia1.py
30 3 * * * /home/bitnami/venv/bin/python3 /home/bitnami/motor_scrapers/auto_health_raia2.py
0 4 * * * /home/bitnami/venv/bin/python3 /home/bitnami/motor_consolidado/auto_health_raia3.py"

(crontab -l | grep -v "auto_health_raia"; echo "$CRON_JOB") | crontab -
echo "Sucesso! As três rotinas de auto-cura foram injetadas na tabela do CRON para a madrugada."
