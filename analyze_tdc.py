import re

filename = '/home/bitnami/homepage_tdc_tier1.txt'
with open(filename, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# find all blocks that look like [td_flex_block... ] or [td_block... ]
blocks = re.findall(r'\[(td_flex_block_[^\s]+)([^\]]+)\]', content)

print(f"Total blocks found: {len(blocks)}\n")

for i, (btype, attrs) in enumerate(blocks):
    title_match = re.search(r'custom_title="([^"]*)"', attrs)
    cat_match = re.search(r'category_ids?="([^"]*)"', attrs)
    tag_match = re.search(r'tag_slug="([^"]*)"', attrs)
    
    title = title_match.group(1) if title_match else "N/A"
    cat = cat_match.group(1) if cat_match else "N/A"
    tag = tag_match.group(1) if tag_match else "N/A"
    
    print(f"Block {i+1}: {btype}")
    print(f"  Title: {title}")
    print(f"  Category: {cat}")
    print(f"  Tag: {tag}")
    print("-" * 40)
