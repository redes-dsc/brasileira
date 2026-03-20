import json
import logging
import sys
import shutil
import datetime
import os
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/home/bitnami/motor_scrapers")
from motor_scrapers_v2 import coletar_links_fonte
from detector_estrategia import detectar_feed_nao_padrao

LOG_FILE = "/home/bitnami/logs/health_autoroutines.log"
SCRAPERS_FILE = "/home/bitnami/motor_scrapers/scrapers.json"
BACKUP_FILE = f"/home/bitnami/motor_scrapers/scrapers_backup_{datetime.datetime.now().strftime('%Y%m%d')}.json"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("Raia2_AutoHealth")

def process_fonte(fonte):
    nome = fonte.get("nome", "Desconhecido")
    is_active = fonte.get("ativo", False)
    estrategia = fonte.get("estrategia", "A")
    
    if not is_active or estrategia not in ("A", "", None):
        return fonte, False
        
    try:
        # Silencia os logs do motor core
        logging.getLogger("motor_scrapers").setLevel(logging.CRITICAL)
        links = coletar_links_fonte(fonte)
        
        if not links:
            url = fonte.get("url_noticias") or fonte.get("url_home", "")
            feed_url = detectar_feed_nao_padrao(url)
            if feed_url:
                fonte["estrategia"] = "D"
                fonte["url_feed"] = feed_url
                logger.warning(f"Correcao Automatica | {nome} | Estrategia A -> D (Injetado RSS: {feed_url})")
                return fonte, True
            else:
                logger.info(f"Falha de raspagem em {nome}, mas nenhum RSS encontrado.")
    except Exception as e:
        logger.error(f"Erro ignorado na saude de {nome}: {e}")
        
    return fonte, False

def main():
    logger.info("Iniciando rotina de auto-cura Motor Scrapers (Raia 2)...")
    if not os.path.exists(SCRAPERS_FILE):
        return
        
    shutil.copy2(SCRAPERS_FILE, BACKUP_FILE)
    
    with open(SCRAPERS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    fontes = data.get("scrapers", [])
    
    modified_count = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(process_fonte, fontes))
        
    updated_fontes = []
    for f_data, modified in results:
        updated_fontes.append(f_data)
        if modified:
            modified_count += 1
            
    if modified_count > 0:
        data["scrapers"] = updated_fontes
        with open(SCRAPERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Raia 2 Concluida! {modified_count} sites recuperados para Estrategia D.")
    else:
        logger.info("Raia 2 Concluida! Sem sites recuperados/alterados hoje.")
        os.remove(BACKUP_FILE)

if __name__ == "__main__":
    main()
