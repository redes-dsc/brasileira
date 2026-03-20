
# -*- coding: utf-8 -*-

import os



arquivo = '/home/bitnami/gestor_wp.py'



try:

    with open(arquivo, 'r', encoding='utf-8') as f:

        codigo = f.read()

except FileNotFoundError:

    print("[ERRO] O arquivo gestor_wp.py nao foi encontrado!")

    exit()



if 'def obter_autor_id_exato' not in codigo:

    nova_funcao = """\n

# --- Funcao injetada automaticamente para o Motor Mestre ---

def obter_autor_id_exato(nome_fonte):

    try:

        from config_categorias import ID_REDACAO, MAPA_AUTORES

        mapa = MAPA_AUTORES

    except ImportError:

        try:

            from config_categorias import ID_REDACAO, MAPA_UNIFICADO_AUTORES

            mapa = MAPA_UNIFICADO_AUTORES

        except ImportError:

            return 2 # Fallback de seguranca

            

    if not nome_fonte: return ID_REDACAO

    

    nome_l = str(nome_fonte).lower()

    for chave, id_autor in mapa.items():

        if chave in nome_l:

            return id_autor

            

    return ID_REDACAO

"""

    with open(arquivo, 'a', encoding='utf-8') as f:

        f.write(nova_funcao)

    print("[OK] Funcao 'obter_autor_id_exato' inserida com sucesso no gestor_wp.py!")

else:

    print("[OK] A funcao ja existia. Nenhuma alteracao necessaria.")

