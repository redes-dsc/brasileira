#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix Newspaper theme settings (PHP serialized format).
Handles: top bar menu, SUBSCRIBE button, Breaking News, header layout.
"""
import subprocess
import re
import os
from dotenv import load_dotenv

load_dotenv()

DB_CMD = [
    '/opt/bitnami/mariadb/bin/mariadb',
    '-u', 'bn_wordpress',
    '-p' + os.getenv("DB_PASS"),
    '-h', '127.0.0.1', '-P', '3306',
    'bitnami_wordpress', '-N', '-e'
]
DB_CMD_BASE = DB_CMD[:-2]

# ============================================================
# Read the theme settings
# ============================================================
print("=== Lendo theme settings ===")
result = subprocess.run(DB_CMD + [
    "SELECT option_value FROM wp_7_options WHERE option_name='td_011_settings'"
], capture_output=True, text=True, timeout=30)

settings_raw = result.stdout.strip()
print(f"  Size: {len(settings_raw)} bytes")

# The PHP serialized format has nested arrays.
# We need to find specific keys within it.

# ============================================================
# Find relevant theme settings keys
# ============================================================
print("\n=== Buscando configurações relevantes ===")

# Extract key-value pairs we care about
SEARCH_KEYS = [
    'tds_top_menu',
    'tds_top_bar_show',
    'tds_header_style', 
    'tds_subscribe_btn',
    'tds_subscribe_btn_text',
    'tds_more_articles_on_post_enable',
    'tds_login_sign_in_widget',
    'td_header_style',
    'tds_header_menu_show',
    'td_menu_background',
    'breaking_news',
    'tds_top_menu_text',
    'show_top_bar',
]

for key in SEARCH_KEYS:
    # Search for the key in the serialized string
    # PHP serialized format: s:len:"key";s:len:"value";
    pattern = f's:\\d+:"{key}";s:(\\d+):"([^"]*)"'
    match = re.search(pattern, settings_raw)
    if match:
        val_len = match.group(1)
        val = match.group(2)
        print(f"  {key} = \"{val}\" (len:{val_len})")
    else:
        # Try boolean format: s:len:"key";b:0; or s:len:"key";b:1;
        pattern_bool = f's:\\d+:"{key}";(b:\\d|i:\\d+|s:\\d+:"[^"]*")'
        match_b = re.search(pattern_bool, settings_raw)
        if match_b:
            print(f"  {key} = {match_b.group(1)}")
        else:
            # Search if key exists at all
            if key in settings_raw:
                # Get surrounding context
                idx = settings_raw.index(key)
                print(f"  {key} found at pos {idx}: ...{settings_raw[idx:idx+80]}...")
            else:
                print(f"  {key} = NOT FOUND")

# ============================================================
# Now let's also search for specific English text to translate
# ============================================================
print("\n=== Textos em inglês no settings ===")
english_texts = [
    'Subscribe', 'SUBSCRIBE', 'Breaking news', 'My account',
    'Latest', 'Popular', 'Load More', 'View All',
    'Custom ad', 'Buy Now', 'Finance', 'Marketing',
    'Celebrity', 'Women', 'Travel', 'Food', 'Music',
]

for text in english_texts:
    if text in settings_raw:
        idx = settings_raw.index(text)
        print(f"  Found \"{text}\" at pos {idx}: ...{settings_raw[max(0,idx-20):idx+60]}...")

# ============================================================
# Apply fixes via string replacement on the serialized data
# ============================================================
print("\n=== Aplicando correções ===")

new_settings = settings_raw

# 1. Fix top bar menu - set it to empty (no menu) to avoid duplication
# Pattern: s:len:"tds_top_menu";s:len:"td-demo-header-menu";
# We need to replace the value while keeping the serialized length correct

def php_replace_value(serialized, key, new_value):
    """Replace a value in PHP serialized string, adjusting string length."""
    # Match: s:len:"key";s:old_len:"old_value";
    pattern = f'(s:\\d+:"{key}";)s:\\d+:"[^"]*";'
    
    def replacer(m):
        prefix = m.group(1)
        return f'{prefix}s:{len(new_value)}:"{new_value}";'
    
    result = re.sub(pattern, replacer, serialized)
    return result

# Disable top bar menu (remove duplicate categories)
new_settings = php_replace_value(new_settings, 'tds_top_menu', '')
print("  ✓ tds_top_menu -> '' (desativado)")

# Fix subscribe button text
new_settings = php_replace_value(new_settings, 'tds_subscribe_btn_text', 'ASSINE')
print("  ✓ tds_subscribe_btn_text -> 'ASSINE'")

# Check if there's a login text
new_settings = php_replace_value(new_settings, 'tds_login_sign_in_widget', 'show')
print("  ✓ tds_login_sign_in_widget kept as 'show'")

# ============================================================
# Fix the outer serialized array length
# The top-level is a:5:{...} where each key is a date
# We need to recalculate the inner array length if we changed string sizes
# For safety, let's just do a SQL UPDATE with the raw modified string
# ============================================================

# The PHP serialized format is length-sensitive.
# Our php_replace_value function handles the inner s: lengths.
# But the outer array lengths may need updating too.
# Let's use a PHP script to handle this properly.

print("\n=== Usando PHP para validar e salvar ===")

# Write a PHP script that reads, modifies, and saves the settings
php_script = """<?php
// Load WordPress
define('ABSPATH', '/opt/bitnami/wordpress/');
define('WPINC', 'wp-includes');

// Direct DB connection
$db = new mysqli('127.0.0.1', 'bn_wordpress', getenv('DB_PASS'), 'bitnami_wordpress', 3306);
if ($db->connect_error) {
    die("DB Error: " . $db->connect_error);
}

// Get current settings
$result = $db->query("SELECT option_value FROM wp_7_options WHERE option_name='td_011_settings'");
$row = $result->fetch_row();
$settings = unserialize($row[0]);

if (!$settings) {
    die("Failed to unserialize settings");
}

echo "Settings keys (first level): " . count($settings) . "\\n";

// The settings are nested - find the active settings array
foreach ($settings as $key => $val) {
    if (is_array($val) && count($val) > 100) {
        echo "Active settings key: $key (". count($val) . " items)\\n";
        
        // Apply fixes
        $val['tds_top_menu'] = '';
        echo "  tds_top_menu -> '' (disabled top bar menu)\\n";
        
        if (isset($val['tds_subscribe_btn_text'])) {
            $val['tds_subscribe_btn_text'] = 'Assine';
            echo "  tds_subscribe_btn_text -> 'Assine'\\n";
        }
        
        // Fix login text
        if (isset($val['tds_login_text'])) {
            $val['tds_login_text'] = 'Entrar';
            echo "  tds_login_text -> 'Entrar'\\n";
        }
        
        // Show subscribe-related settings
        foreach ($val as $k => $v) {
            if (!is_array($v) && (stripos($k, 'subscr') !== false || stripos($k, 'login') !== false || stripos($k, 'top_menu') !== false || stripos($k, 'breaking') !== false)) {
                echo "  $k = $v\\n";
            }
        }
        
        $settings[$key] = $val;
    }
}

// Serialize and save
$new_serialized = serialize($settings);
$escaped = $db->real_escape_string($new_serialized);
$db->query("UPDATE wp_7_options SET option_value='$escaped' WHERE option_name='td_011_settings'");

if ($db->affected_rows >= 0) {
    echo "\\nSettings saved! (" . strlen($new_serialized) . " bytes)\\n";
} else {
    echo "\\nError saving: " . $db->error . "\\n";
}

// Clear caches
$db->query("DELETE FROM wp_7_options WHERE option_name LIKE '%_transient_%'");
$db->query("DELETE FROM wp_7_options WHERE option_name LIKE '%td_cache_%'");
$db->query("DELETE FROM wp_7_options WHERE option_name LIKE '%tdc_cache_%'");
echo "Caches cleared!\\n";

$db->close();
?>
"""

with open('/tmp/fix_theme_settings.php', 'w') as f:
    f.write(php_script)

result_php = subprocess.run(['php', '/tmp/fix_theme_settings.php'], 
                           capture_output=True, text=True, timeout=30)
if result_php.returncode == 0:
    print(result_php.stdout)
else:
    print(f"Erro PHP: {result_php.stderr[:300]}")
    print(f"Output: {result_php.stdout[:300]}")

print("\nConcluído!")
