import sys
import logging
import datetime
import requests

sys.path.insert(0, "/home/bitnami/motor_consolidado")
sys.path.insert(0, "/home/bitnami")

from config_consolidado import TIER1_PORTALS, TIER2_PORTALS
from alerta_notificacao import enviar_alerta

LOG_FILE = "/home/bitnami/logs/health_autoroutines.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("Raia3_AutoHealth")

def main():
    logger.info("Iniciando auditoria corretiva TIER 1 e 2 (Motor Consolidado)...")
    try:
        portals = TIER1_PORTALS + TIER2_PORTALS
    except Exception as e:
        logger.error("Portais nao foram montados corretamente!")
        return

    if not portals:
        logger.critical("Listagem de portais vazia (config_consolidado quebrado?)")
        enviar_alerta("ERRO: Listagem de TIER1/2 Portals esgotada na Raia3. Verifique configs.", nivel="CRITICAL")
        return

    erros_acumulados = 0
    for portal in portals:
        nome = portal.get("name", "Desconhecido")
        url = portal.get("url", "")
        if not url: continue
        
        try:
            # Pings directly to make sure the endpoint has not locked out the server entirely or timeout.
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}, verify=False)
            if r.status_code >= 400:
                logger.critical(f"ALERTA VERMELHO: {nome} retornou HTTP {r.status_code}!")
                erros_acumulados += 1
            else:
                logger.info(f"{nome} OK: Atingivel ({r.status_code}).")
        except Exception as e:
            logger.critical(f"ALERTA VERMELHO: Timeout/Conexao do portal {nome} travou com erro: {e}")
            erros_acumulados += 1

    if erros_acumulados > 2:
        try:
            enviar_alerta(f"Health Raia 3: Multiplos ({erros_acumulados}) portais TIER indisponiveis! Cheque proxy de rede urgente.", nivel="CRITICAL")
        except: pass
            
    logger.info("Auditoria Raia 3 Concluida.")

if __name__ == "__main__":
    main()
