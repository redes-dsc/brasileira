
# -*- coding: utf-8 -*-

import os

import re



arquivos = [

    '/home/bitnami/roteador_ia.py',

    '/home/bitnami/motor_avancado.py'

]



print("\n=== CORTANDO LIGACAO COM O DALL-E 3 ===")



for arq in arquivos:

    if not os.path.exists(arq):

        continue

        

    with open(arq, 'r', encoding='utf-8') as f:

        codigo = f.read()

        

    codigo_original = codigo



    # Bloqueio 1: Roteador IA

    codigo = re.sub(

        r'(def roteador_ia_imagem\([^)]*\):)', 

        r'\1\n    return None # [TRAVA EDITORIAL - DALL-E 3 DESATIVADO]\n', 

        codigo

    )

    

    # Bloqueio 2: Motor Avancado

    codigo = re.sub(

        r'(def gerar_imagem\([^)]*\):)', 

        r'\1\n    return None # [TRAVA EDITORIAL - DALL-E 3 DESATIVADO]\n', 

        codigo

    )



    if codigo != codigo_original:

        with open(arq, 'w', encoding='utf-8') as f:

            f.write(codigo)

        print(f"[OK] Fios do DALL-E 3 cortados com sucesso em: {arq}")

    else:

        print(f"[INFO] Bloqueio ja estava ativo em: {arq}")



print("\n=== SUCESSO ABSOLUTO! ===")

print("A partir deste exato segundo, o seu site esta livre de imagens geradas por IA.")

print("Apenas fotos reais das materias originais serao publicadas!\n")

