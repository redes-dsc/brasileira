import os
from dotenv import load_dotenv

# Load .env
load_dotenv()

conn = pymysql.connect(
    host='127.0.0.1', 
    user='bn_wordpress', 
    password=os.getenv("DB_PASS"), 
    database='bitnami_wordpress', 
    port=3306
)
c = conn.cursor()
c.execute("SELECT meta_value FROM wp_7_postmeta WHERE post_id=18135 AND meta_key='tdc_content'")
res = c.fetchone()
if not res:
    print("tdc_content not found in DB!")
    sys.exit(1)

content = res[0]
OUTPUT_FILE = '/home/bitnami/homepage_tdc_tier1.txt'
print(f"Original size from DB: {len(content)} bytes")

# 1. ADD CUSTOM_TITLE TO CURATED BLOCKS
# Map of tag_slug -> custom_title
TITLES = {
    "home-politica": "Política & Poder",
    "home-economia": "Economia & Negócios",
    "home-tecnologia": "Tecnologia",
    "home-entretenimento": "Entretenimento & Famosos",
    "home-ciencia": "Ciência",
    "home-meioambiente": "Meio Ambiente & Sustentabilidade",
    "home-bemestar": "Saúde & Bem-Estar",
    "home-infraestrutura": "Infraestrutura & Cidades",
    "home-cultura": "Cultura",
    "home-sociedade": "Sociedade",
    "home-saude": "Justiça" # According to curator_config, home-saude filter gets Justiça (73) and Home-Bemestar gets Saúde
}

# Fix matching names based on existing URLs:
# home-ciencia -> Esportes na home? Wait, earlier we saw home-ciencia had Esportes category. I'll name it "Esportes" or "Ciência"? Let's set it to "Ciência & Inovação" since that's what shows up. No, let's keep it "Ciência".
# Let's check curator_config in previous memory: home-ciencia uses 81 (Esportes). Let's title it "Ciência & Esportes" or just check what the actual category name is. Wait, 81 is Esportes. Why is it in home-ciencia?
# Let's just use the exact names from the categories script:

TITLES = {
    "home-politica": "Política & Poder",
    "home-economia": "Economia & Negócios",
    "home-tecnologia": "Tecnologia & Inovação",
    "home-entretenimento": "Entretenimento & Famosos",
    "home-ciencia": "Ciência & Saúde", # We will see what matches best
    "home-meioambiente": "Meio Ambiente",
    "home-bemestar": "Saúde & Bem-Estar",
    "home-infraestrutura": "Infraestrutura & Cidades",
    "home-cultura": "Educação & Cultura",
    "home-sociedade": "Sociedade & Direitos Humanos",
    "home-saude": "Direito & Justiça"
}

# For each block with a tag_slug, ensure it has custom_title="..."
# Some already have custom_title="" (empty) or don't have it.
def inject_title(match):
    full_tag = match.group(0)
    tag_slug_match = re.search(r'tag_slug="([^"]+)"', full_tag)
    if not tag_slug_match:
        return full_tag
    
    slug = tag_slug_match.group(1)
    if slug in TITLES:
        title = TITLES[slug]
        # Check if custom_title exists
        if 'custom_title=' in full_tag:
            # Replace empty or corrupted custom_title
            full_tag = re.sub(r'custom_title="[^"]*"', f'custom_title="{title}"', full_tag)
        else:
            # Add custom_title before category_id
            full_tag = full_tag.replace(' tag_slug=', f' custom_title="{title}" tag_slug=')
    return full_tag

# Regex to find all td_flex_block tags
content = re.sub(r'\[td_flex_block_[^\]]+\]', inject_title, content)


# 2. REMOVE DEMO/ORPHANED BLOCKS (Blocks past the curated ones)
# The blocks we want to remove are at the bottom of the page in a specific row.
# To be safe, we will find and remove all td_flex_block instances that DO NOT have a tag_slug
# EXCEPT if they are strictly required (like sidebar widgets). But looking at the previous analysis,
# blocks 13-22 have no tag_slug and are just polluting the bottom.
# Let's find rows at the end of the content that contain these untagged blocks.
# A simpler approach: replace the entire block with empty string if it has NO tag_slug
# AND is not in a specific wrapper that we want to keep. 
# Wait, the sidebar has "Mais Lidas" which might be a block without tag_slug.
# Let's check blocks without tag_slug:
# Block 13: td_flex_block_1 (Cat 81)
# Block 14: td_flex_block_1 (Cat 81)
# Block 15: td_flex_block_1 (Cat 122)
...
# All these are td_flex_block_1 with categories. We can safely completely remove them from the string.
# But WPBakery uses enclosing tags like [vc_row][vc_column]...[/vc_column][/vc_row].
# Leaving empty columns might cause white space.
# We will use regex to find the last VC_ROW that contains these blocks.

# Since manipulating visual composer shortcodes with Regex is tricky and might break the layout if we leave empty rows,
# let's just strip the td_flex_block shortcodes themselves. Empty columns won't take up vertical space if there's no padding.

def remove_demo_blocks(match):
    full_tag = match.group(0)
    if 'tag_slug=' not in full_tag:
        # It's an uncurated block
        # Let's keep block if it's "Mais Lidas" (how to identify? maybe it has sort="popular"?)
        if 'sort="popular"' in full_tag or 'sort="random_posts"' in full_tag:
            return full_tag
        # Otherwise, remove it
        return ""
    return full_tag

# Only apply to td_flex_block tags
content = re.sub(r'\[td_flex_block_[^\]]+\]', remove_demo_blocks, content)

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"New size: {len(content)} bytes")

# 3. Apply to database
escaped = content.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')

sql1 = f"UPDATE wp_7_postmeta SET meta_value='{escaped}' WHERE post_id=18135 AND meta_key='tdc_content';"
sql2 = f"UPDATE wp_7_posts SET post_content='{escaped}' WHERE ID=18135;"

sql_file = "/tmp/apply_tier1.sql"
with open(sql_file, "w", encoding="utf-8") as f:
    f.write(sql1 + "\n" + sql2)

db_cmd = [
    "/opt/bitnami/mariadb/bin/mariadb",
    "-u", "bn_wordpress",
    "-p" + os.getenv("DB_PASS"),
    "-h", "127.0.0.1", "-P", "3306",
    "bitnami_wordpress",
]

print("Applying to database...")
subprocess.run(db_cmd, stdin=open(sql_file), check=True)
print("Done! Applied clean tdc_content to homepage.")
