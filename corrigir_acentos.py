
import os



arquivos = ['/home/bitnami/motor_mestre.py', '/home/bitnami/motor_scrapers.py']



for arq in arquivos:

    if os.path.exists(arq):

        with open(arq, 'rb') as f:

            dados = f.read()

        try:

            dados.decode('utf-8')

            print(f"[OK] {arq} ja esta no formato correto.")

        except UnicodeDecodeError:

            # Força a conversão do acento antigo para o padrão UTF-8

            texto = dados.decode('latin-1')

            with open(arq, 'w', encoding='utf-8') as f:

                f.write(texto)

            print(f"[CORRIGIDO] {arq} convertido com sucesso para UTF-8!")

