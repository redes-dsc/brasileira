import pymysql
import re
import base64
import os
from dotenv import load_dotenv

load_dotenv()

DB_USER = "bn_wordpress"
DB_PASS = os.getenv("DB_PASS")
DB_NAME = "bitnami_wordpress"
PUB_ID = os.getenv('ADSENSE_PUB_ID')

def run_homogenization():
    print("Conectando ao banco de dados...")
    conn = pymysql.connect(host="127.0.0.1", user=DB_USER, password=DB_PASS, database=DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT post_id, meta_value FROM wp_7_postmeta WHERE meta_key='tdc_content'")
    rows = cursor.fetchall()
    updates = 0
    total_matches = 0

    for row in rows:
        post_id = row[0]
        content = row[1]
        
        if not content or "custom_ad_code=" not in content:
            continue

        def replacer(match):
            nonlocal total_matches
            raw_b64 = match.group(1)
            try:
                decoded = base64.b64decode(raw_b64).decode('utf-8')
                
                # Vamos substituir o data-ad-client="ca-pub-XXXXXXXXX" pelo pub ID real
                # E também certificar que as aspas estao blindadas
                new_decoded = re.sub(r'data-ad-client=["\']ca-pub-[^"\']*["\']', f'data-ad-client="{PUB_ID}"', decoded)
                
                if new_decoded != decoded:
                    total_matches += 1
                    new_b64 = base64.b64encode(new_decoded.encode('utf-8')).decode('utf-8')
                    return f'custom_ad_code="{new_b64}"'
            except Exception as e:
                pass
            
            return match.group(0)

        new_content = re.sub(r'custom_ad_code="([^"]+)"', replacer, content)
        
        if new_content != content:
            print(f"  -> Injetando AdSense oficial no Template/Post ID: {post_id}")
            cursor.execute("UPDATE wp_7_postmeta SET meta_value=%s WHERE post_id=%s AND meta_key='tdc_content'", (new_content, post_id))
            updates += 1

    if updates > 0:
        conn.commit()
        print(f"\n✅ SUCESSO! {updates} templates/páginas atualizados. Total de blocos de Ads substituídos: {total_matches}")
    else:
        print("\nℹ️ Nenhuma marcação passível de alteração foi encontrada.")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    run_homogenization()
