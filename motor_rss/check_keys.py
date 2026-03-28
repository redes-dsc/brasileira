#!/usr/bin/env python3
"""Verifica todas as API keys configuradas no .env"""
import os, sys, time
sys.path.insert(0, "/home/bitnami/motor_rss")
import config

results = {}

# --- GEMINI ---
for i, suffix in enumerate(["", "_2", "_3"], 1):
    key = os.getenv(f"GEMINI_API_KEY{suffix}", "")
    if not key:
        results[f"gemini_{i}"] = "MISSING"
        continue
    try:
        from google import genai
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(model="gemini-2.5-flash", contents="Responda apenas: OK")
        results[f"gemini_{i}"] = f"OK ({resp.text.strip()[:20]})"
    except Exception as e:
        results[f"gemini_{i}"] = f"ERRO: {str(e)[:100]}"
    time.sleep(1)

# --- GROK ---
for i, suffix in enumerate(["", "_2", "_3"], 1):
    key = os.getenv(f"GROK_API_KEY{suffix}", "")
    if not key:
        results[f"grok_{i}"] = "MISSING"
        continue
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url="https://api.x.ai/v1")
        resp = client.chat.completions.create(model="grok-2-latest", messages=[{"role":"user","content":"Responda apenas: OK"}], max_tokens=10, timeout=30)
        results[f"grok_{i}"] = f"OK ({resp.choices[0].message.content.strip()[:20]})"
    except Exception as e:
        results[f"grok_{i}"] = f"ERRO: {str(e)[:100]}"
    time.sleep(1)

# --- PERPLEXITY ---
for i, suffix in enumerate(["", "_2", "_3"], 1):
    key = os.getenv(f"PERPLEXITY_API_KEY{suffix}", "")
    if not key:
        results[f"perplexity_{i}"] = "MISSING"
        continue
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url="https://api.perplexity.ai")
        resp = client.chat.completions.create(model="sonar-pro", messages=[{"role":"user","content":"Responda apenas: OK"}], max_tokens=10, timeout=30)
        results[f"perplexity_{i}"] = f"OK ({resp.choices[0].message.content.strip()[:20]})"
    except Exception as e:
        results[f"perplexity_{i}"] = f"ERRO: {str(e)[:100]}"
    time.sleep(1)

# --- OPENAI ---
for i, suffix in enumerate(["", "_2", "_3"], 1):
    key = os.getenv(f"OPENAI_API_KEY{suffix}", "")
    if not key:
        results[f"openai_{i}"] = "MISSING"
        continue
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":"Responda apenas: OK"}], max_tokens=10, timeout=30)
        results[f"openai_{i}"] = f"OK ({resp.choices[0].message.content.strip()[:20]})"
    except Exception as e:
        results[f"openai_{i}"] = f"ERRO: {str(e)[:100]}"
    time.sleep(1)

# --- CLAUDE ---
for i, suffix in enumerate(["", "_2", "_3"], 1):
    key = os.getenv(f"ANTHROPIC_API_KEY{suffix}", "")
    if not key:
        results[f"claude_{i}"] = "MISSING"
        continue
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key, timeout=30)
        resp = client.messages.create(model="claude-3-5-haiku-20241022", max_tokens=10, messages=[{"role":"user","content":"Responda apenas: OK"}])
        results[f"claude_{i}"] = f"OK ({resp.content[0].text.strip()[:20]})"
    except Exception as e:
        results[f"claude_{i}"] = f"ERRO: {str(e)[:100]}"
    time.sleep(1)

# --- DEEPSEEK (novas) ---
for i, key in enumerate(config.DEEPSEEK_KEYS, 1):
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(model="deepseek-chat", messages=[{"role":"user","content":"Responda apenas: OK"}], max_tokens=10, timeout=30)
        results[f"deepseek_{i}"] = f"OK ({resp.choices[0].message.content.strip()[:20]})"
    except Exception as e:
        results[f"deepseek_{i}"] = f"ERRO: {str(e)[:100]}"
    time.sleep(1)

# --- ALIBABA/QWEN (novas) ---
for i, key in enumerate(config.QWEN_KEYS, 1):
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
        resp = client.chat.completions.create(model="qwen-plus", messages=[{"role":"user","content":"Responda apenas: OK"}], max_tokens=10, timeout=30)
        results[f"qwen_{i}"] = f"OK ({resp.choices[0].message.content.strip()[:20]})"
    except Exception as e:
        results[f"qwen_{i}"] = f"ERRO: {str(e)[:100]}"
    time.sleep(1)

print("\n=== RESULTADO DA VERIFICAÇÃO DE API KEYS ===\n")
for k, v in results.items():
    status = "✅" if v.startswith("OK") else "❌"
    print(f"  {status} {k:20s} → {v}")
print(f"\nTotal: {sum(1 for v in results.values() if v.startswith('OK'))}/{len(results)} funcionando")
