import sys
import os
from navegador import Navegador
import portal_bb

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)
from bd import database

def run():
    """Função principal que orquestra todo o processo de RPA."""
    
    # 1. Inicializa o banco de dados
    database.inicializar_banco()

    # 2. Busca as tarefas pendentes
    solicitacoes_pendentes = database.obter_solicitacoes_pendentes()
    if not solicitacoes_pendentes:
        print("✅ Nenhuma solicitação pendente encontrada. Trabalho concluído!")
        return
    print(f"📂 {len(solicitacoes_pendentes)} solicitações pendentes para processar.")

    # 3. Inicia o navegador
    nav = Navegador()
    try:
        nav.iniciar()
        
        # 4. Faz o login
        portal_page = portal_bb.fazer_login(nav.context)

        # 5. Processa cada solicitação pendente
        total = len(solicitacoes_pendentes)
        for i, numero in enumerate(solicitacoes_pendentes):
            print(f"\n[🔄] Processando {i+1}/{total}: {numero}")
            try:
                dados_completos = portal_bb.coletar_detalhes(portal_page, numero)
                
                # Usa a nova função para ATUALIZAR os detalhes no banco de dados
                database.atualizar_detalhes_solicitacao(dados_completos)
                
                print(f"✅ Dados de {numero} atualizados com sucesso!")
            except Exception as e:
                print(f"❌ Erro ao processar {numero}: {e}")
        
        print("\n🏁 Fim da coleta de dados detalhados.")

    except Exception as e:
        print(f"\n========================= ERRO CRÍTICO =========================")
        print(f"Ocorreu uma falha na automação: {e}")
        print(f"================================================================")
    finally:
        # 6. Fecha o navegador
        print("\n... Fechando o navegador e encerrando o script ...")
        nav.fechar()

if __name__ == "__main__":
    run()