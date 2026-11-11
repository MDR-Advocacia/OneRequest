"""Executa UM ciclo completo dos robôs (números → detalhes → status) e sai.

Usado pelo endpoint POST /api/rpa/executar para disparos manuais.
Diferente do run_robos.py, não tem loop de agendamento — roda e termina.
"""
import sys
from run_robos import ciclo_completo_de_automacao

if __name__ == "__main__":
    sucesso = ciclo_completo_de_automacao()
    sys.exit(0 if sucesso else 1)
