
# -*- coding: utf-8 -*-
# ⚠️ DEPRECATED — Este script está DESATIVADO.
#
# Motivo: Injetava código em gestor_wp.py via regex em produção, referenciando
# buscar_e_subir_imagem_real() que nunca foi implementada (causaria NameError).
# A lógica de garantia de imagens agora é responsabilidade do
# curador_imagens_unificado.py (Tiers 1-5 + placeholder).
#
# Para reativar, exija ENABLE_GARANTIA_IMAGENS=1 no .env.

import os
import sys

if os.getenv("ENABLE_GARANTIA_IMAGENS", "0") != "1":
    print("[garantia_imagens.py] DESATIVADO. Usar curador_imagens_unificado.py.")
    sys.exit(0)

# Código original abaixo nunca executará sem a env var.
print("[ERRO] garantia_imagens.py não deve ser usado. Use curador_imagens_unificado.py.")
sys.exit(1)

