#!/usr/bin/env python3
"""
Configurar Google AdSense — brasileira.news
============================================
Script de gestão completa da integração AdSense no portal.

Uso:
  python3 configurar_adsense.py diagnostico          # Ver estado atual
  python3 configurar_adsense.py criar_ads_txt PUB_ID # Criar ads.txt
  python3 configurar_adsense.py instalar PUB_ID      # Configuração completa
  python3 configurar_adsense.py article_ads CODE      # Inserir Article Ads
  python3 configurar_adsense.py limpar_demos          # Remover ads demo
  python3 configurar_adsense.py rollback              # Reverter alterações

Conta AdSense: redes@descompli.ca
"""

import sys
import os
import re
import json
import subprocess
import shutil
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ─── Configuração ───
DB_USER = "bn_wordpress"
DB_PASS = os.getenv("DB_PASS")
DB_HOST = "127.0.0.1"
DB_PORT = "3306"
DB_NAME = "bitnami_wordpress"
MARIADB = "/opt/bitnami/mariadb/bin/mariadb"
WP_ROOT = "/opt/bitnami/wordpress"
TABLE_PREFIX = "wp_7_"

# IDs dos templates
SINGLE_POST_TEMPLATE_ID = 18256
HOMEPAGE_ID = 18135
HOMEPAGE_MOBILE_ID = 18415

# IDs das imagens demo a remover
DEMO_AD_IMAGES = [18122, 18123, 18126, 18417]

# Diretório de backups
BACKUP_DIR = os.path.expanduser("~/backups_adsense")

# ─── Utilitários DB ───
def executar_sql(sql, fetchone=False):
    """Executa SQL no WordPress e retorna resultado."""
    cmd = [MARIADB, "-u", DB_USER, f"-p{DB_PASS}", "-h", DB_HOST,
           "-P", DB_PORT, DB_NAME, "-N", "-e", sql]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise Exception(f"SQL Error: {result.stderr}")
    return result.stdout.strip()


def executar_sql_raw(sql):
    """Executa SQL e retorna bytes brutos."""
    cmd = [MARIADB, "-u", DB_USER, f"-p{DB_PASS}", "-h", DB_HOST,
           "-P", DB_PORT, DB_NAME, "-N", "-e", sql]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0:
        raise Exception(f"SQL Error: {result.stderr.decode()}")
    return result.stdout.strip()


# ─── Backup ───
def fazer_backup(label):
    """Cria backup dos dados relevantes antes de modificar."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"adsense_backup_{label}_{timestamp}.json")

    backups = {}

    # Backup do td_011 (theme options)
    td011 = executar_sql(
        f"SELECT option_value FROM {TABLE_PREFIX}options WHERE option_name='td_011'"
    )
    backups["td_011"] = td011

    # Backup do tdc_content de templates com ads
    for post_id in [SINGLE_POST_TEMPLATE_ID, HOMEPAGE_ID, HOMEPAGE_MOBILE_ID]:
        content = executar_sql(
            f"SELECT meta_value FROM {TABLE_PREFIX}postmeta "
            f"WHERE post_id={post_id} AND meta_key='tdc_content'"
        )
        backups[f"tdc_content_{post_id}"] = content

    # Backup do ads.txt se existir
    ads_txt_path = os.path.join(WP_ROOT, "ads.txt")
    if os.path.exists(ads_txt_path):
        with open(ads_txt_path, "r") as f:
            backups["ads_txt"] = f.read()

    with open(backup_file, "w") as f:
        json.dump(backups, f, indent=2)

    print(f"  ✅ Backup salvo: {backup_file}")
    return backup_file


# ─── Diagnóstico ───
def diagnostico():
    """Mostra o estado atual da configuração de ads."""
    print("\n" + "=" * 60)
    print("  DIAGNÓSTICO AdSense — brasileira.news")
    print("=" * 60)

    # 1. ads.txt
    ads_txt = os.path.join(WP_ROOT, "ads.txt")
    print(f"\n📄 ads.txt: ", end="")
    if os.path.exists(ads_txt):
        with open(ads_txt, "r") as f:
            content = f.read().strip()
        print(f"✅ Existe ({len(content)} chars)")
        for line in content.split("\n")[:5]:
            print(f"   {line}")
    else:
        print("❌ NÃO existe")

    # 2. AdSense no <head>
    print(f"\n🔗 AdSense snippet no site: ", end="")
    try:
        result = subprocess.run(
            ["curl", "-s", "https://brasileira.news/"],
            capture_output=True, text=True, timeout=15
        )
        if "adsbygoogle" in result.stdout or "pagead2" in result.stdout:
            print("✅ Código AdSense detectado no HTML")
        else:
            print("❌ Nenhum código AdSense no HTML")
    except Exception:
        print("⚠️  Não foi possível verificar (curl falhou)")

    # 3. Ad Box elements nos templates
    print(f"\n📦 Ad Box elements nos templates:")
    for name, pid in [("Single Post Template", SINGLE_POST_TEMPLATE_ID),
                       ("Homepage Desktop", HOMEPAGE_ID),
                       ("Homepage Mobile", HOMEPAGE_MOBILE_ID)]:
        content = executar_sql(
            f"SELECT meta_value FROM {TABLE_PREFIX}postmeta "
            f"WHERE post_id={pid} AND meta_key='tdc_content'"
        )
        ad_count = content.count("td_block_ad_box") if content else 0
        has_adsense = "adsbygoogle" in content if content else False
        has_demo = any(str(img_id) in content for img_id in DEMO_AD_IMAGES) if content else False

        status = []
        if ad_count > 0:
            status.append(f"{ad_count} ad box(es)")
        else:
            status.append("sem ad box")
        if has_adsense:
            status.append("🟢 AdSense")
        if has_demo:
            status.append("🟡 Demo images")

        print(f"   {name} (ID {pid}): {', '.join(status)}")

    # 4. Theme Panel ad_code
    print(f"\n⚙️  Theme Panel ad_code slots:")
    td011 = executar_sql(
        f"SELECT option_value FROM {TABLE_PREFIX}options WHERE option_name='td_011'"
    )
    ad_code_count = td011.count('"ad_code"') if td011 else 0
    ad_codes_with_content = 0
    if td011:
        # Find ad_code entries that have non-empty values
        matches = re.findall(r'"ad_code";s:(\d+):"', td011)
        ad_codes_with_content = sum(1 for m in matches if int(m) > 0)

    print(f"   Total slots: ~{ad_code_count}")
    print(f"   Com conteúdo: {ad_codes_with_content}")

    # 5. Article Ads no Single Post Content
    print(f"\n📝 Article Ads (Single Post Content element):")
    if SINGLE_POST_TEMPLATE_ID:
        spt_content = executar_sql(
            f"SELECT meta_value FROM {TABLE_PREFIX}postmeta "
            f"WHERE post_id={SINGLE_POST_TEMPLATE_ID} AND meta_key='tdc_content'"
        )
        for ad_type in ["article_top_ad", "article_inline_ad", "article_inline_ad2",
                         "article_inline_ad3", "article_bottom_ad"]:
            if spt_content and ad_type in spt_content:
                print(f"   {ad_type}: ✅ Configurado")
            else:
                print(f"   {ad_type}: ❌ Vazio")

    # 6. Header template
    print(f"\n🔝 Header Template:")
    header_ids = executar_sql(
        f"SELECT ID, post_title FROM {TABLE_PREFIX}posts "
        f"WHERE post_type='tdb_templates' AND post_title LIKE '%Header%' "
        f"AND post_status='publish' ORDER BY ID"
    )
    if header_ids:
        for line in header_ids.split("\n"):
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                hid = parts[0]
                htitle = parts[1]
                hcontent = executar_sql(
                    f"SELECT meta_value FROM {TABLE_PREFIX}postmeta "
                    f"WHERE post_id={hid} AND meta_key='tdc_content'"
                )
                has_ad = "ad_box" in (hcontent or "")
                print(f"   {htitle} (ID {hid}): {'✅ Tem ad' if has_ad else '❌ Sem ad'}")
    else:
        print("   Nenhum header template encontrado")

    print("\n" + "=" * 60)


# ─── Criar ads.txt ───
def criar_ads_txt(publisher_id):
    """Cria o arquivo ads.txt no root do WordPress."""
    if not publisher_id.startswith("pub-"):
        publisher_id = f"pub-{publisher_id}"
    ca_pub = f"ca-{publisher_id}" if not publisher_id.startswith("ca-") else publisher_id
    pub_only = publisher_id.replace("ca-", "").replace("pub-", "")

    ads_txt_path = os.path.join(WP_ROOT, "ads.txt")

    content = f"""# ads.txt - brasileira.news
# Conta AdSense: redes@descompli.ca
# Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

google.com, pub-{pub_only}, DIRECT, f08c47fec0942fa0
"""

    with open(ads_txt_path, "w") as f:
        f.write(content)

    # Ajustar permissões
    os.chmod(ads_txt_path, 0o644)

    print(f"  ✅ ads.txt criado: {ads_txt_path}")
    print(f"  📋 Publisher ID: pub-{pub_only}")
    print(f"  🔗 Verificar: https://brasileira.news/ads.txt")
    return ads_txt_path


# ─── Limpar Ads Demo ───
def limpar_demos():
    """Remove os ad boxes com imagens demo dos templates."""
    print("\n🧹 Limpando ads demo dos templates...")

    fazer_backup("limpar_demos")

    changes = 0

    # Single Post Template (18256) - tem 2 ad boxes com imagens demo
    content = executar_sql(
        f"SELECT meta_value FROM {TABLE_PREFIX}postmeta "
        f"WHERE post_id={SINGLE_POST_TEMPLATE_ID} AND meta_key='tdc_content'"
    )
    if content:
        for img_id in DEMO_AD_IMAGES:
            if f'spot_img_all="{img_id}"' in content:
                # Remove the entire ad_box shortcode
                pattern = r'\[td_block_ad_box[^\]]*spot_img_all="' + str(img_id) + r'"[^\]]*\]'
                new_content = re.sub(pattern, '', content)
                if new_content != content:
                    content = new_content
                    changes += 1
                    print(f"   ✅ Removido ad demo (image {img_id}) do Single Post Template")

        if changes > 0:
            # Escape the content for SQL
            escaped = content.replace("\\", "\\\\").replace("'", "\\'")
            executar_sql(
                f"UPDATE {TABLE_PREFIX}postmeta SET meta_value='{escaped}' "
                f"WHERE post_id={SINGLE_POST_TEMPLATE_ID} AND meta_key='tdc_content'"
            )

    # Homepage Mobile (18415) - tem 1 ad box demo
    content_mob = executar_sql(
        f"SELECT meta_value FROM {TABLE_PREFIX}postmeta "
        f"WHERE post_id={HOMEPAGE_MOBILE_ID} AND meta_key='tdc_content'"
    )
    if content_mob:
        for img_id in DEMO_AD_IMAGES:
            if f'spot_img_all="{img_id}"' in content_mob:
                pattern = r'\[td_block_ad_box[^\]]*spot_img_all="' + str(img_id) + r'"[^\]]*\]'
                new_content_mob = re.sub(pattern, '', content_mob)
                if new_content_mob != content_mob:
                    content_mob = new_content_mob
                    changes += 1
                    print(f"   ✅ Removido ad demo (image {img_id}) da Homepage Mobile")

        if changes > 0:
            escaped = content_mob.replace("\\", "\\\\").replace("'", "\\'")
            executar_sql(
                f"UPDATE {TABLE_PREFIX}postmeta SET meta_value='{escaped}' "
                f"WHERE post_id={HOMEPAGE_MOBILE_ID} AND meta_key='tdc_content'"
            )

    print(f"\n   Total de ads demo removidos: {changes}")
    return changes


# ─── Gerar código AdSense ───
def gerar_adsense_code(publisher_id, slot_id=None, format_type="auto", layout=None):
    """Gera o snippet HTML do AdSense para um slot."""
    pub_clean = publisher_id.replace("ca-", "").replace("pub-", "")

    code = '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-{pub}" crossorigin="anonymous"></script>\n'
    code += '<ins class="adsbygoogle"\n'
    code += '     style="display:block"\n'

    if slot_id:
        code += f'     data-ad-client="ca-pub-{pub_clean}"\n'
        code += f'     data-ad-slot="{slot_id}"\n'
    else:
        code += f'     data-ad-client="ca-pub-{pub_clean}"\n'

    if format_type:
        code += f'     data-ad-format="{format_type}"\n'

    if layout:
        code += f'     data-ad-layout="{layout}"\n'

    code += '     data-full-width-responsive="true"></ins>\n'
    code += '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>'

    return code.replace("{pub}", pub_clean)


# ─── Instalar configuração completa ───
def instalar(publisher_id):
    """Configuração completa do AdSense — ads.txt + head snippet + article ads."""
    pub_clean = publisher_id.replace("ca-", "").replace("pub-", "")

    print("\n" + "=" * 60)
    print("  INSTALAÇÃO AdSense — brasileira.news")
    print(f"  Publisher ID: pub-{pub_clean}")
    print(f"  Conta: redes@descompli.ca")
    print("=" * 60)

    # Backup
    print("\n1️⃣  Criando backup...")
    fazer_backup("instalar_completa")

    # ads.txt
    print("\n2️⃣  Criando ads.txt...")
    criar_ads_txt(pub_clean)

    # Head snippet via Newspaper Theme Panel (td_011)
    print("\n3️⃣  Nota sobre snippet do AdSense no <head>:")
    print("   ⚠️  O snippet de verificação do AdSense deve ser adicionado via:")
    print("   Newspaper > Theme Panel > Custom CSS / JS")
    print("   OU via plugin Header/Footer (ex: Insert Headers and Footers)")
    print(f"   Código: <script async src=\"https://pagead2.googlesyndication.com/"
          f"pagead/js/adsbygoogle.js?client=ca-pub-{pub_clean}\" "
          f"crossorigin=\"anonymous\"></script>")

    # Gerar códigos de exemplo para cada posição
    print("\n4️⃣  Códigos AdSense para cada posição:")
    print("   (Criar slots individuais no painel AdSense para melhor tracking)\n")

    positions = [
        ("Article Top Ad", "auto", None),
        ("Article Inline Ad", "fluid", "in-article"),
        ("Article Bottom Ad", "auto", None),
        ("Sidebar 300x250", "auto", None),
        ("Header Leaderboard", "auto", None),
        ("Homepage Between Sections", "auto", None),
    ]

    for name, fmt, layout in positions:
        code = gerar_adsense_code(pub_clean, format_type=fmt, layout=layout)
        print(f"   📌 {name}:")
        print(f"   {'-' * 40}")
        for line in code.split("\n"):
            print(f"   {line}")
        print()

    # Instruções de implementação
    print("\n5️⃣  Próximos passos (requer tagDiv Composer):")
    print("   a. Article Ads: Editar Single Post Template (ID 18256)")
    print("      → Single Post Content element → Ads tab")
    print("      → Colar códigos nos campos Top / Inline / Bottom")
    print("   b. Sidebar: Editar Ad Box element existente")
    print("      → Custom Ad tab → Colar código")
    print("   c. Homepage: Editar Homepage (ID 18135)")
    print("      → Adicionar Ad Box element → Custom Ad tab")
    print("   d. Header: Editar Header Template")
    print("      → Adicionar Ad Box element abaixo do menu")

    print("\n" + "=" * 60)


# ─── Configurar Article Ads via DB ───
def configurar_article_ads(adsense_code):
    """Insere código de ad nas posições do Single Post Content element no template."""
    print("\n📝 Configurando Article Ads no Single Post Template...")

    fazer_backup("article_ads")

    content = executar_sql(
        f"SELECT meta_value FROM {TABLE_PREFIX}postmeta "
        f"WHERE post_id={SINGLE_POST_TEMPLATE_ID} AND meta_key='tdc_content'"
    )

    if not content:
        print("   ❌ Template de Single Post não encontrado!")
        return False

    # Check if tdb_single_content element exists
    if "tdb_single_content" not in content:
        print("   ❌ Elemento tdb_single_content não encontrado no template!")
        print("   ℹ️  Os Article Ads devem ser configurados via tagDiv Composer")
        print(f"   🔗 Editar: WP Admin > Posts > Template ID {SINGLE_POST_TEMPLATE_ID}")
        return False

    # The tdb_single_content element in the template shortcode
    # We need to add article ad attributes to it
    # Format: article_top_ad="<encoded_ad_code>" article_inline_ad="<encoded>" article_bottom_ad="<encoded>"

    # Base64 encode the ad code for the shortcode attribute (Newspaper uses base64 for some attrs)
    import base64
    encoded_code = base64.b64encode(adsense_code.encode()).decode()

    modified = False

    # Add article_top_ad if not present
    if 'article_top_ad=' not in content:
        content = content.replace(
            '[tdb_single_content',
            f'[tdb_single_content article_top_ad="{encoded_code}"'
        )
        modified = True
        print("   ✅ Article Top Ad adicionado")

    # Add article_inline_ad
    if 'article_inline_ad=' not in content:
        content = content.replace(
            '[tdb_single_content',
            f'[tdb_single_content article_inline_ad="{encoded_code}" inline_ad_paragraph="3"'
        )
        modified = True
        print("   ✅ Article Inline Ad adicionado (após 3º parágrafo)")

    # Add article_bottom_ad
    if 'article_bottom_ad=' not in content:
        content = content.replace(
            '[tdb_single_content',
            f'[tdb_single_content article_bottom_ad="{encoded_code}"'
        )
        modified = True
        print("   ✅ Article Bottom Ad adicionado")

    if modified:
        escaped = content.replace("\\", "\\\\").replace("'", "\\'")
        executar_sql(
            f"UPDATE {TABLE_PREFIX}postmeta SET meta_value='{escaped}' "
            f"WHERE post_id={SINGLE_POST_TEMPLATE_ID} AND meta_key='tdc_content'"
        )
        print("   ✅ Template atualizado no banco de dados")
    else:
        print("   ℹ️  Article Ads já estão configurados")

    return modified


# ─── Rollback ───
def rollback():
    """Restaura a partir do backup mais recente."""
    if not os.path.exists(BACKUP_DIR):
        print("❌ Nenhum backup encontrado!")
        return

    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith(".json")])
    if not backups:
        print("❌ Nenhum backup encontrado!")
        return

    print(f"\n📂 Backups disponíveis:")
    for i, b in enumerate(backups):
        print(f"   [{i}] {b}")

    latest = backups[-1]
    print(f"\n🔄 Restaurando do backup mais recente: {latest}")

    with open(os.path.join(BACKUP_DIR, latest), "r") as f:
        data = json.load(f)

    # Restaurar td_011
    if "td_011" in data and data["td_011"]:
        escaped = data["td_011"].replace("\\", "\\\\").replace("'", "\\'")
        executar_sql(
            f"UPDATE {TABLE_PREFIX}options SET option_value='{escaped}' "
            f"WHERE option_name='td_011'"
        )
        print("   ✅ td_011 restaurado")

    # Restaurar tdc_content
    for key, value in data.items():
        if key.startswith("tdc_content_") and value:
            post_id = key.split("_")[-1]
            escaped = value.replace("\\", "\\\\").replace("'", "\\'")
            executar_sql(
                f"UPDATE {TABLE_PREFIX}postmeta SET meta_value='{escaped}' "
                f"WHERE post_id={post_id} AND meta_key='tdc_content'"
            )
            print(f"   ✅ tdc_content do post {post_id} restaurado")

    # Restaurar ads.txt
    if "ads_txt" in data:
        with open(os.path.join(WP_ROOT, "ads.txt"), "w") as f:
            f.write(data["ads_txt"])
        print("   ✅ ads.txt restaurado")

    print("\n✅ Rollback concluído!")


# ─── Main ───
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    comando = sys.argv[1].lower()

    if comando == "diagnostico":
        diagnostico()

    elif comando == "criar_ads_txt":
        if len(sys.argv) < 3:
            print("❌ Uso: python3 configurar_adsense.py criar_ads_txt PUB_ID")
            sys.exit(1)
        criar_ads_txt(sys.argv[2])

    elif comando == "instalar":
        if len(sys.argv) < 3:
            print("❌ Uso: python3 configurar_adsense.py instalar PUB_ID")
            sys.exit(1)
        instalar(sys.argv[2])

    elif comando == "article_ads":
        if len(sys.argv) < 3:
            print("❌ Uso: python3 configurar_adsense.py article_ads 'ADSENSE_CODE'")
            sys.exit(1)
        configurar_article_ads(sys.argv[2])

    elif comando == "limpar_demos":
        limpar_demos()

    elif comando == "rollback":
        rollback()

    else:
        print(f"❌ Comando desconhecido: {comando}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
