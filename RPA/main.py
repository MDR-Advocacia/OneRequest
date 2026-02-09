import sys
import os
import time

# Garante a importação dos módulos
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from bd import database
from nav_selenium import NavSelenium
import portal_bb
import coletaDadosNumeroSolicitacoes

def run():
    print("🎬 Iniciando RPA OneRequest (Versão Selenium Final)...")
    database.inicializar_banco()

    # 1. Inicia o Navegador
    nav = NavSelenium()
    driver = None
    
    try:
        driver = nav.iniciar()
        
        # 2. Realiza o Login
        if not nav.fazer_login():
            print("❌ Abortando: Falha no login.")
            return

        # 3. Sincronização (Opcional: se quiser pular essa etapa para ser mais rápido na correção, comente a linha abaixo)
        print("\n=== ETAPA 1: Sincronização de Listagem ===")
        coletaDadosNumeroSolicitacoes.sincronizar_solicitacoes(driver)

        # 4. Busca Itens para Processar (Novos + Falhas Anteriores)
        novas = database.obter_solicitacoes_pendentes()
        incompletas = database.obter_solicitacoes_incompletas()
        
        # Remove duplicatas e cria lista única
        solicitacoes_para_processar = list(set(novas + incompletas))
        
        if not solicitacoes_para_processar:
            print("\n✅ Nenhuma solicitação pendente ou incompleta.")
        else:
            print(f"\n=== ETAPA 2: Coleta de Detalhes ({len(solicitacoes_para_processar)} itens) ===")
            print(f"   (Sendo {len(novas)} novas e {len(incompletas)} reprocessamentos)")
            
            total = len(solicitacoes_para_processar)
            for i, numero in enumerate(solicitacoes_para_processar):
                print(f"\n[🔄] Processando {i+1}/{total}: {numero}")
                try:
                    # Chama o portal_bb blindado
                    dados_completos = portal_bb.coletar_detalhes(driver, numero)
                    
                    if dados_completos:
                        # Validação extra: Se falhar o DMI de novo, avisa no log
                        if not dados_completos.get("texto_dmi"):
                            print(f"⚠️ Atenção: {numero} continuou sem Texto DMI.")
                        
                        database.atualizar_detalhes_solicitacao(dados_completos)
                        print(f"✅ Dados salvos!")
                    else:
                        print(f"⚠️ Dados vazios retornados para {numero}")
                        
                except Exception as e:
                    print(f"❌ Erro ao processar {numero}: {e}")

        print("\n🏁 Fim da execução global.")

    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO: {e}")
    finally:
        nav.fechar()

if __name__ == "__main__":
    run()