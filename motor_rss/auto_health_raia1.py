import json
import time
import requests
import feedparser
import datetime
import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor
import os
import shutil
import sys

sys.path.insert(0, "/home/bitnami")
from alerta_notificacao import enviar_alerta

LOG_FILE = "/home/bitnami/logs/health_autoroutines.log"
FEEDS_FILE = "/home/bitnami/motor_rss/feeds.json"
BACKUP_FILE = f"/home/bitnami/motor_rss/feeds_backup_{datetime.datetime.now().strftime('%Y%m%d')}.json"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("Raia1_AutoHealth")

def check_feed(f_data):
    feed_data = dict(f_data) # Safe copy to avoid dict mutation in thread
    nome = feed_data.get("nome", "Desconhecido")
    url = feed_data.get("url", "")
    ativo = feed_data.get("ativo", False)
    
    if not ativo:
        return feed_data, False
        
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"}, verify=False)
        # Handle all deadly statuses
        if r.status_code in (401, 403, 404, 410, 500, 502, 503):
            logger.warning(f"Desativando {nome}: URL Retornou HTTP {r.status_code}.")
            feed_data["ativo"] = False
            try:
                enviar_alerta(f"Feed desativado ({r.status_code}): {nome}", nivel="WARNING")
            except: pass
            return feed_data, True
            
        parsed = feedparser.parse(r.text)
        entries = getattr(parsed, "entries", [])
        
        latest_time = None
        for entry in entries[:15]: # Look deeper just in case of sticky posts
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
                try:
                    enviar_alerta(f"Feed desativado (inativo {days_ago}d): {nome}", nivel="WARNING")
                except: pass
                return feed_data, True
                
        return feed_data, False
        
    except Exception as e:
        logger.error(f"Erro ignorado ao checar {nome}: {e}")
        return feed_data, False

def main():
    logger.info("Iniciando rotina de saude do Motor RSS (Raia 1)...")
    if not os.path.exists(FEEDS_FILE):
        return
        
    # Backup
    try:
        shutil.copy2(FEEDS_FILE, BACKUP_FILE)
    except Exception:
        pass
    
    with open(FEEDS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    feeds = data.get("feeds", [])
    
    modified_count = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(check_feed, feeds))
        
    updated_feeds = []
    for f_data, modified in results:
        updated_feeds.append(f_data)
        if modified:
            modified_count += 1
            
    # Max disable limit to prevent empty-outs
    if modified_count > (len(feeds) * 0.2):
        logger.error("Abortando: Muitos feeds falharam no ciclo (>20%). Possível queda de DNS da máquina.")
        return

    if modified_count > 0:
        data["feeds"] = updated_feeds
        with tempfile.NamedTemporaryFile("w", dir=os.path.dirname(FEEDS_FILE), delete=False, encoding="utf-8") as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            temp_name = tmp.name
        os.replace(temp_name, FEEDS_FILE)
        logger.info(f"Concluido! {modified_count} feeds desativados.")
    else:
        logger.info("Concluido! Nenhuma alteracao necessaria no feeds.json.")
        try:
            os.remove(BACKUP_FILE)
        except Exception:
            pass

if __name__ == "__main__":
    main()
