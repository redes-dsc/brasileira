import json
import time
import requests
import feedparser
import datetime
import logging
from concurrent.futures import ThreadPoolExecutor
import os
import shutil

LOG_FILE = "/home/bitnami/logs/health_autoroutines.log"
FEEDS_FILE = "/home/bitnami/motor_rss/feeds.json"
BACKUP_FILE = f"/home/bitnami/motor_rss/feeds_backup_{datetime.datetime.now().strftime('%Y%m%d')}.json"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("Raia1_AutoHealth")

def check_feed(feed_data):
    nome = feed_data.get("nome", "Desconhecido")
    url = feed_data.get("url", "")
    ativo = feed_data.get("ativo", False)
    
    if not ativo:
        return feed_data, False
        
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 404:
            logger.warning(f"Desativando {nome}: URL Retornou HTTP 404.")
            feed_data["ativo"] = False
            return feed_data, True
            
        parsed = feedparser.parse(r.text)
        entries = getattr(parsed, "entries", [])
        
        latest_time = None
        for entry in entries[:5]:
            t = getattr(entry, "published_parsed", getattr(entry, "updated_parsed", None))
            if t:
                try:
                    dt = datetime.datetime.fromtimestamp(time.mktime(t))
                    if latest_time is None or dt > latest_time:
                        latest_time = dt
                except: pass
        
        if latest_time:
            days_ago = (datetime.datetime.now() - latest_time).days
            if days_ago > 90:
                logger.warning(f"Desativando {nome}: Inativo há {days_ago} dias (>90).")
                feed_data["ativo"] = False
                return feed_data, True
                
        return feed_data, False
        
    except Exception as e:
        logger.error(f"Erro ao checar {nome}: {e}")
        return feed_data, False

def main():
    logger.info("Iniciando rotina de saude do Motor RSS (Raia 1)...")
    if not os.path.exists(FEEDS_FILE):
        return
        
    # Backup
    shutil.copy2(FEEDS_FILE, BACKUP_FILE)
    
    with open(FEEDS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    feeds = data.get("feeds", [])
    
    modified_count = 0
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(check_feed, feeds))
        
    updated_feeds = []
    for f_data, modified in results:
        updated_feeds.append(f_data)
        if modified:
            modified_count += 1
            
    if modified_count > 0:
        data["feeds"] = updated_feeds
        with open(FEEDS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Concluido! {modified_count} feeds desativados.")
    else:
        logger.info("Concluido! Nenhuma alteracao necessaria no feeds.json.")
        os.remove(BACKUP_FILE) # remove empty backup

if __name__ == "__main__":
    main()
