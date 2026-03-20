import sys
import logging
import datetime

sys.path.insert(0, "/home/bitnami/motor_scrapers")
sys.path.insert(0, "/home/bitnami/motor_consolidado")
sys.path.insert(0, "/home/bitnami")

from scraper_homes import scrape_portal_titles
from config_consolidado import TIER1_PORTALS, TIER2_PORTALS

LOG_FILE = "/home/bitnami/logs/health_autoroutines.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("Raia3_AutoHealth")

def main():
    logger.info("Iniciando auditoria de endpoints urgentes TIER 1 e 2 (Motor Consolidado)...")
    portals = TIER1_PORTALS + TIER2_PORTALS
    
    for portal in portals:
        nome = portal.get("name", "Desconhecido")
        try:
            links = scrape_portal_titles(portal)
            if not links:
                logger.critical(f"ALERTA VERMELHO: {nome} retornou 0 manchetes! Verifique se a estrutura mudou ou fomos bloqueados.")
            else:
                logger.info(f"{nome} OK: {len(links)} manchetes extradas na analise de home.")
        except Exception as e:
            logger.critical(f"ALERTA VERMELHO: O extrator HTML/RSS do portal {nome} travou com erro: {e}")
            
    logger.info("Auditoria Raia 3 Concluida.")

if __name__ == "__main__":
    main()
