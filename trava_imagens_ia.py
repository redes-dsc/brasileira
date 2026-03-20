
# -*- coding: utf-8 -*-

"""

TRAVA EDITORIAL - Brasileira.news

Desativa a geracao de imagens alucinadas por IA para manter a credibilidade.

"""

import os

import re



arquivos = [

    '/home/bitnami/motor_mestre.py', 

    '/home/bitnami/motor_scrapers.py', 

    '/home/bitnami/gestor_wp.py'

]



print("\n=== ATIVANDO TRAVA EDITORIAL DE IMAGENS ===")



for arq in arquivos:

    if not os.path.exists(arq):

        continue

        

    with open(arq, 'r', encoding='utf-8') as f:

        codigo = f.read()

        

    codigo_original = codigo



    # 1. Neutraliza qualquer função que se chame 'gerar_imagem_ia' ou similar

    codigo = re.sub(

        r'(def\s+gerar_imagem[^:]+:\s*\n)', 

        r'\1    return None # [TRAVA EDITORIAL] Geracao de IA bloqueada para evitar alucinacoes\n', 

        codigo

    )

    

    # 2. Neutraliza chamadas diretas à IA na hora de definir a URL da imagem

    codigo = re.sub(

        r'(url_imagem\s*=\s*gerar_imagem_ia\([^)]+\))', 

        r'url_imagem = None # [TRAVA EDITORIAL] IA desativada', 

        codigo

    )



    if codigo != codigo_original:

        with open(arq, 'w', encoding='utf-8') as f:

            f.write(codigo)

        print(f"[OK] Fios cortados e IA desativada em: {arq}")

    else:

        print(f"[INFO] Nenhuma chamada ativa de IA encontrada em: {arq}")



print("\n=== SUCESSO! ===")

print("A partir de agora, os robos SO vao usar as fotos REAIS das agencias.")

print("Se a noticia original nao tiver foto, a materia subira sem imagem (o que preserva a sua credibilidade).\n")

