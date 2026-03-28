import json
import logging
import sys
import shutil
import datetime
import tempfile
import requests
import os
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/home/bitnami/motor_scrapers")
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

def process_fonte(f_orig):
    fonte = dict(f_orig) # Assuring immutability copy
    nome = fonte.get("nome", "Desconhecido")
    is_active = fonte.get("ativo", False)
    estrategia = fonte.get("estrategia", "A")
    
    # Allows recovery of "D" if the original URL is now functional
    if not is_active:
        return fonte, False
        
    url = fonte.get("url_noticias") or fonte.get("url_home", "")
    if not url: return fonte, False
    
    try:
        # Pings homepage quickly instead of scraping production models heavily
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            if estrategia == "D":
                logger.info(f"Fonte recuperada: {nome}")
            return fonte, False # It's UP.
        
        # If it's failing, try injecting RSS feed auto-correction
        feed_url = detectar_feed_nao_padrao(url)
        if feed_url and estrategia != "D":
            fonte["estrategia"] = "D"
            fonte["url_feed"] = feed_url
            logger.warning(f"Correcao Automatica | {nome} | -> D (RSS: {feed_url})")
            return fonte, True
            
        logger.info(f"Falha de raspagem em {nome}, nenhum RSS detectado.")
    except Exception as e:
        logger.error(f"Erro ignorado na saude de {nome}: {e}")
        
    return fonte, False

def main():
    logger.info("Iniciando rotina de ping-healing Motor Scrapers (Raia 2)...")
    if not os.path.exists(SCRAPERS_FILE):
        return
        
    try:
        shutil.copy2(SCRAPERS_FILE, BACKUP_FILE)
    except Exception: pass
    
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
        with tempfile.NamedTemporaryFile("w", dir=os.path.dirname(SCRAPERS_FILE), delete=False, encoding="utf-8") as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            temp_name = tmp.name
        os.replace(temp_name, SCRAPERS_FILE)
        logger.info(f"Raia 2 Concluida! {modified_count} sites recuperados para Estrategia D.")
    else:
        logger.info("Raia 2 Concluida! Sem sites alterados hoje.")
        try:
            os.remove(BACKUP_FILE)
        except: pass

if __name__ == "__main__":
    main()
