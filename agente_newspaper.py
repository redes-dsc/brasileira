#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AGENTE NEWSPAPER - Gestor Inteligente do Tema Newspaper (tagDiv)
Recebe briefings em linguagem natural, mapeia componentes e caminhos,
e coordena/implementa mudanças no tema WordPress.

Integra com:
  - newspaper_knowledge.db (SQLite - knowledge base)
  - llm_router (41 modelos em 7 providers)
  - gestor_wp.py, reorganizar_homepage.py, aplicar_homepage.py (scripts existentes)
  - WordPress REST API & MariaDB direto
"""

import sqlite3
import json
import os
import sys
import subprocess
import time
from datetime import datetime

# Importar roteador de IA
sys.path.insert(0, '/home/bitnami')
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'motor_rss'))
import llm_router

DB_PATH = '/home/bitnami/newspaper_knowledge.db'

# Credenciais do banco WordPress (do .env)
WP_DB_USER = 'bn_wordpress'
import os
from dotenv import load_dotenv

load_dotenv()

WP_DB_PASS = os.getenv("DB_PASS")
WP_DB_HOST = '127.0.0.1'
WP_DB_PORT = '3306'
WP_DB_NAME = 'bitnami_wordpress'
MARIADB_BIN = '/opt/bitnami/mariadb/bin/mariadb'


# =============================================
# CLASSE PRINCIPAL DO AGENTE
# =============================================

class AgenteNewspaper:
    """Agente inteligente para gestão do tema Newspaper."""

    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        print("[AGENTE] Newspaper Agent inicializado.")
        print(f"[AGENTE] Knowledge base: {DB_PATH}")

    def close(self):
        self.conn.close()

    # ----- CONSULTAS AO KNOWLEDGE BASE -----

    def buscar_documentacao(self, termo):
        """Busca documentação por termo."""
        c = self.conn.cursor()
        c.execute("""
            SELECT section_name, doc_url, category, summary, instructions
            FROM doc_sections
            WHERE section_name LIKE ? OR summary LIKE ? OR instructions LIKE ?
            ORDER BY CASE WHEN instructions IS NOT NULL THEN 0 ELSE 1 END
            LIMIT 10
        """, (f'%{termo}%', f'%{termo}%', f'%{termo}%'))
        return [dict(r) for r in c.fetchall()]

    def buscar_componente(self, nome_ou_tipo):
        """Busca componente do tema."""
        c = self.conn.cursor()
        c.execute("""
            SELECT component_name, component_type, wp_location, db_table, db_key, notes
            FROM theme_components
            WHERE component_name LIKE ? OR component_type LIKE ? OR notes LIKE ?
            LIMIT 10
        """, (f'%{nome_ou_tipo}%', f'%{nome_ou_tipo}%', f'%{nome_ou_tipo}%'))
        return [dict(r) for r in c.fetchall()]

    def buscar_acao(self, verbo=None, alvo=None):
        """Busca caminho de ação."""
        c = self.conn.cursor()
        conditions, params = [], []
        if verbo:
            conditions.append("action_verb LIKE ?")
            params.append(f'%{verbo}%')
        if alvo:
            conditions.append("(target LIKE ? OR instructions LIKE ?)")
            params.extend([f'%{alvo}%', f'%{alvo}%'])
        where = " AND ".join(conditions) if conditions else "1=1"
        c.execute(f"""
            SELECT action_verb, target, wp_admin_path, api_endpoint, db_path,
                   python_script, method, instructions
            FROM action_paths WHERE {where} LIMIT 10
        """, params)
        return [dict(r) for r in c.fetchall()]

    def buscar_categoria(self, nome_ou_id):
        """Busca categoria."""
        c = self.conn.cursor()
        try:
            wp_id = int(nome_ou_id)
            c.execute("SELECT * FROM wp_categories WHERE wp_id = ?", (wp_id,))
        except (ValueError, TypeError):
            c.execute("SELECT * FROM wp_categories WHERE name LIKE ? OR slug LIKE ?",
                      (f'%{nome_ou_id}%', f'%{nome_ou_id}%'))
        return [dict(r) for r in c.fetchall()]

    def buscar_configuracao(self, chave_ou_grupo):
        """Busca configuração do tema."""
        c = self.conn.cursor()
        c.execute("""
            SELECT setting_key, setting_value, setting_group, description
            FROM theme_settings
            WHERE setting_key LIKE ? OR setting_group LIKE ? OR description LIKE ?
        """, (f'%{chave_ou_grupo}%', f'%{chave_ou_grupo}%', f'%{chave_ou_grupo}%'))
        return [dict(r) for r in c.fetchall()]

    def listar_categorias(self, tipo=None):
        """Lista todas as categorias (macro ou sub)."""
        c = self.conn.cursor()
        if tipo:
            c.execute("SELECT * FROM wp_categories WHERE category_type = ? ORDER BY name", (tipo,))
        else:
            c.execute("SELECT * FROM wp_categories ORDER BY category_type, name")
        return [dict(r) for r in c.fetchall()]

    # ----- EXECUÇÃO DE SQL NO WORDPRESS -----

    def executar_sql_wp(self, sql, salvar=False):
        """Executa SQL no banco WordPress via mariadb CLI."""
        env = os.environ.copy()
        env['MYSQL_PWD'] = WP_DB_PASS
        cmd = [
            MARIADB_BIN, '-u', WP_DB_USER,
            '-h', WP_DB_HOST, '-P', WP_DB_PORT, WP_DB_NAME, '-N', '-e', sql
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
            if result.returncode != 0:
                return {'sucesso': False, 'erro': result.stderr.strip()}
            return {'sucesso': True, 'resultado': result.stdout.strip()}
        except Exception as e:
            return {'sucesso': False, 'erro': str(e)}

    # ----- REGISTRO DE ALTERAÇÕES -----

    def registrar_alteracao(self, briefing, acao, componente, old_val, new_val, status, rollback_sql=None):
        """Registra ação no change_log."""
        c = self.conn.cursor()
        c.execute("""
            INSERT INTO change_log (timestamp, briefing, action_taken, target_component,
                                    old_value, new_value, status, rollback_sql)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), briefing, acao, componente,
              str(old_val)[:5000] if old_val else None,
              str(new_val)[:5000] if new_val else None,
              status, rollback_sql))
        self.conn.commit()

    def ver_historico(self, limite=10):
        """Ver últimas alterações."""
        c = self.conn.cursor()
        c.execute("SELECT * FROM change_log ORDER BY id DESC LIMIT ?", (limite,))
        return [dict(r) for r in c.fetchall()]

    # ----- INTEPRETAÇÃO DE BRIEFING VIA IA -----

    def interpretar_briefing(self, briefing):
        """Usa IA para interpretar um briefing e identificar ações necessárias."""
        # Montar contexto do knowledge base
        componentes = self.conn.cursor().execute(
            "SELECT component_name, component_type FROM theme_components"
        ).fetchall()
        lista_comp = ", ".join([f"{r['component_name']}({r['component_type']})" for r in componentes])

        acoes = self.conn.cursor().execute(
            "SELECT DISTINCT action_verb || ' ' || target AS acao FROM action_paths"
        ).fetchall()
        lista_acoes = ", ".join([r['acao'] for r in acoes])

        categorias = self.conn.cursor().execute(
            "SELECT wp_id, name FROM wp_categories WHERE category_type='macro'"
        ).fetchall()
        lista_cats = ", ".join([f"{r['name']}(id:{r['wp_id']})" for r in categorias])

        system_prompt = f"""Você é o agente especialista do tema Newspaper (tagDiv) para o site Brasileira.News.
Seu papel é interpretar briefings do editor-chefe e mapear para ações técnicas.

COMPONENTES DISPONÍVEIS: {lista_comp}

AÇÕES DISPONÍVEIS: {lista_acoes}

CATEGORIAS MACRO: {lista_cats}

Responda em JSON com esta estrutura:
{{
  "entendimento": "breve resumo do que o usuário quer",
  "acoes": [
    {{
      "verbo": "alterar|adicionar|consultar|publicar|criar|importar",
      "alvo": "nome do componente/alvo",
      "parametros": {{}},
      "metodo_sugerido": "wp_admin|api|database|script",
      "prioridade": 1
    }}
  ],
  "avisos": ["lista de riscos ou cuidados"],
  "requires_confirmation": true
}}"""

        user_prompt = f"BRIEFING DO EDITOR: {briefing}"

        print(f"\n[AGENTE] Interpretando briefing via IA...")
        resultado = llm_router.call_llm(system_prompt=system_prompt, user_prompt=user_prompt + '\n\nRetorne OBRIGATORIAMENTE APENAS um JSON valido puro.', tier=llm_router.TIER_PREMIUM)[0]

        if resultado:
            try:
                parsed = json.loads(resultado)
                return parsed
            except json.JSONDecodeError:
                return {"erro": "Resposta da IA não é JSON válido", "raw": resultado}
        return {"erro": "Falha em todos os motores de IA"}

    def processar_briefing(self, briefing):
        """Interpreta briefing e enriquece com dados do knowledge base."""
        interpretacao = self.interpretar_briefing(briefing)

        if 'erro' in interpretacao:
            return interpretacao

        # Enriquecer cada ação com dados do KB
        for acao in interpretacao.get('acoes', []):
            # Buscar caminho detalhado
            caminhos = self.buscar_acao(acao.get('verbo'), acao.get('alvo'))
            if caminhos:
                acao['caminho_detalhado'] = caminhos[0]

            # Buscar componente
            comps = self.buscar_componente(acao.get('alvo', ''))
            if comps:
                acao['componente_info'] = comps[0]

            # Buscar doc relevante
            docs = self.buscar_documentacao(acao.get('alvo', ''))
            if docs:
                acao['documentacao'] = docs[0]

        # Registrar no log
        self.registrar_alteracao(
            briefing=briefing,
            acao='interpretar_briefing',
            componente=None,
            old_val=None,
            new_val=json.dumps(interpretacao, ensure_ascii=False)[:5000],
            status='interpretado'
        )

        return interpretacao

    # ----- AÇÕES ESPECÍFICAS -----

    def consultar_homepage(self):
        """Consulta o layout atual da homepage."""
        result = self.executar_sql_wp(
            "SELECT LENGTH(meta_value) as tamanho FROM wp_7_postmeta "
            "WHERE post_id=18135 AND meta_key='tdc_content';"
        )
        if result['sucesso']:
            return {'homepage_post_id': 18135, 'tdc_content_size': result['resultado']}
        return result

    def consultar_templates_ativos(self):
        """Lista templates tagDiv ativos."""
        result = self.executar_sql_wp(
            "SELECT ID, post_title, post_name FROM wp_7_posts "
            "WHERE post_type='tdb_templates' AND post_status='publish' ORDER BY post_title;"
        )
        if result['sucesso']:
            templates = []
            for line in result['resultado'].split('\n'):
                if '\t' in line:
                    parts = line.split('\t')
                    templates.append({'id': parts[0], 'title': parts[1], 'name': parts[2] if len(parts) > 2 else ''})
            return templates
        return result

    def consultar_menus(self):
        """Lista menus WordPress."""
        result = self.executar_sql_wp(
            "SELECT t.term_id, t.name, t.slug, tt.count FROM wp_7_terms t "
            "JOIN wp_7_term_taxonomy tt ON t.term_id = tt.term_id "
            "WHERE tt.taxonomy='nav_menu' ORDER BY t.name;"
        )
        if result['sucesso']:
            menus = []
            for line in result['resultado'].split('\n'):
                if '\t' in line:
                    parts = line.split('\t')
                    menus.append({'id': parts[0], 'name': parts[1], 'slug': parts[2], 'items': parts[3]})
            return menus
        return result

    def consultar_opcoes_tema(self, chave=None):
        """Consulta opções do tema no wp_options."""
        if chave:
            chave_segura = chave.replace("'", "").replace('"', "").replace(";", "")
            sql = f"SELECT option_value FROM wp_7_options WHERE option_name='{chave_segura}';"
        else:
            sql = ("SELECT option_name, LEFT(option_value, 200) FROM wp_7_options "
                   "WHERE option_name LIKE '%td_%' OR option_name LIKE '%newspaper%' "
                   "ORDER BY option_name LIMIT 20;")
        return self.executar_sql_wp(sql)

    def contar_posts_categoria(self, cat_id):
        """Conta posts em uma categoria específica."""
        try:
            cat_id_seguro = int(cat_id)
        except ValueError:
            return {'sucesso': False, 'erro': 'ID invalido'}
            
        result = self.executar_sql_wp(
            f"SELECT COUNT(*) FROM wp_7_posts p "
            f"JOIN wp_7_term_relationships tr ON p.ID = tr.object_id "
            f"WHERE tr.term_taxonomy_id = {cat_id_seguro} AND p.post_status = 'publish';"
        )
        return result

    # ----- STATUS GERAL -----

    def status_geral(self):
        """Retorna status geral do tema e site."""
        info = {}

        # Do knowledge base
        c = self.conn.cursor()
        for table in ['doc_sections', 'theme_components', 'action_paths', 'wp_categories', 'change_log']:
            c.execute(f'SELECT COUNT(*) FROM {table}')
            info[f'kb_{table}'] = c.fetchone()[0]

        # Settings
        c.execute("SELECT setting_key, setting_value FROM theme_settings WHERE setting_group='general'")
        for row in c.fetchall():
            info[row['setting_key']] = row['setting_value']

        # Templates ativos
        templates = self.consultar_templates_ativos()
        if isinstance(templates, list):
            info['templates_ativos'] = len(templates)

        # Menus
        menus = self.consultar_menus()
        if isinstance(menus, list):
            info['menus'] = len(menus)

        return info


# =============================================
# INTERFACE CLI
# =============================================

def main():
    """Interface de linha de comando do agente."""
    agente = AgenteNewspaper()

    print("\n" + "=" * 60)
    print("  AGENTE NEWSPAPER - Brasileira.News")
    print("  Gestor Inteligente do Tema Newspaper (tagDiv)")
    print("=" * 60)

    if len(sys.argv) > 1:
        comando = sys.argv[1].lower()

        if comando == 'status':
            status = agente.status_geral()
            print("\n[STATUS GERAL]")
            for k, v in status.items():
                print(f"  {k}: {v}")

        elif comando == 'briefing' and len(sys.argv) > 2:
            briefing = ' '.join(sys.argv[2:])
            resultado = agente.processar_briefing(briefing)
            print("\n[RESULTADO]")
            print(json.dumps(resultado, indent=2, ensure_ascii=False))

        elif comando == 'buscar' and len(sys.argv) > 2:
            tipo = sys.argv[2]
            termo = ' '.join(sys.argv[3:]) if len(sys.argv) > 3 else ''
            if tipo == 'doc':
                results = agente.buscar_documentacao(termo)
            elif tipo == 'componente':
                results = agente.buscar_componente(termo)
            elif tipo == 'acao':
                parts = termo.split(' ', 1)
                results = agente.buscar_acao(parts[0] if parts else None, parts[1] if len(parts) > 1 else None)
            elif tipo == 'categoria':
                results = agente.buscar_categoria(termo)
            elif tipo == 'config':
                results = agente.buscar_configuracao(termo)
            else:
                results = []
                print(f"Tipo desconhecido: {tipo}")

            print(f"\n[{len(results)} resultados]")
            for r in results:
                print(json.dumps(r, indent=2, ensure_ascii=False))

        elif comando == 'categorias':
            tipo = sys.argv[2] if len(sys.argv) > 2 else None
            cats = agente.listar_categorias(tipo)
            print(f"\n[{len(cats)} categorias]")
            for cat in cats:
                prefix = "  " if cat.get('category_type') == 'sub' else ""
                print(f"  {prefix}{cat['name']} (ID: {cat['wp_id']}, posts: {cat.get('post_count', '?')})")

        elif comando == 'templates':
            templates = agente.consultar_templates_ativos()
            print(f"\n[Templates ativos]")
            if isinstance(templates, list):
                for t in templates:
                    print(f"  ID {t['id']}: {t['title']}")
            else:
                print(f"  Erro: {templates}")

        elif comando == 'menus':
            menus = agente.consultar_menus()
            print(f"\n[Menus WordPress]")
            if isinstance(menus, list):
                for m in menus:
                    print(f"  {m['name']} (ID: {m['id']}, items: {m['items']})")

        elif comando == 'historico':
            hist = agente.ver_historico()
            print(f"\n[Últimas {len(hist)} alterações]")
            for h in hist:
                print(f"  [{h['timestamp']}] {h['action_taken']} -> {h['target_component']} ({h['status']})")

        elif comando == 'homepage':
            info = agente.consultar_homepage()
            print(f"\n[Homepage]")
            print(json.dumps(info, indent=2, ensure_ascii=False))

        else:
            print_ajuda()
    else:
        print_ajuda()

    agente.close()


def print_ajuda():
    print("""
USO: python3 agente_newspaper.py <comando> [argumentos]

COMANDOS:
  status                    Status geral do tema e knowledge base
  briefing "texto"          Interpretar briefing do editor via IA
  buscar doc <termo>        Buscar documentação
  buscar componente <termo> Buscar componente do tema
  buscar acao <verbo alvo>  Buscar caminho de ação
  buscar categoria <nome>   Buscar categoria
  buscar config <chave>     Buscar configuração
  categorias [macro|sub]    Listar categorias
  templates                 Listar templates tagDiv ativos
  menus                     Listar menus WordPress
  homepage                  Info da homepage
  historico                 Ver histórico de alterações

EXEMPLOS:
  python3 agente_newspaper.py status
  python3 agente_newspaper.py briefing "Quero trocar a cor principal do site para azul"
  python3 agente_newspaper.py buscar doc header
  python3 agente_newspaper.py buscar acao alterar logo
  python3 agente_newspaper.py categorias macro
""")


if __name__ == '__main__':
    main()
