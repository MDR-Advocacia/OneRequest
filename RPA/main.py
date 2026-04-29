import sys
import os
import time
from navegador import Navegador
import portal_bb
from observability import install_print_logger, log_event, push_robot_metrics

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)
from bd import database

logger = install_print_logger("robo-detalhes")


def processar_com_retentativas(portal_page, numero, max_tentativas, espera_segundos):
    ultimo_erro = None
    for tentativa in range(1, max_tentativas + 1):
        try:
            if tentativa > 1:
                print(f"    - Nova tentativa {tentativa}/{max_tentativas} para {numero}...")
            log_event(
                logger,
                "Iniciando processamento da solicitacao.",
                solicitacao=numero,
                attempt=tentativa,
                status="started",
            )
            dados_completos = portal_bb.coletar_detalhes(portal_page, numero)
            database.atualizar_detalhes_solicitacao(dados_completos)
            log_event(
                logger,
                "Solicitacao atualizada com sucesso.",
                solicitacao=numero,
                attempt=tentativa,
                status="success",
            )
            return True
        except Exception as exc:
            ultimo_erro = exc
            log_event(
                logger,
                f"Falha ao processar solicitacao: {exc}",
                solicitacao=numero,
                attempt=tentativa,
                status="error",
            )
            if tentativa < max_tentativas:
                print(f"⚠️ Tentativa {tentativa}/{max_tentativas} falhou para {numero}: {exc}")
                print(f"    - Aguardando {espera_segundos}s antes de tentar novamente...")
                for page in list(portal_page.context.pages):
                    if page != portal_page:
                        try:
                            page.close()
                        except Exception:
                            pass
                time.sleep(espera_segundos)
                continue
            print(f"❌ Erro ao processar {numero} após {max_tentativas} tentativas: {ultimo_erro}")
            return False


def run():
    """Função principal que orquestra todo o processo de RPA."""
    inicio = time.monotonic()
    log_event(logger, "Execucao do robo de detalhes iniciada.", status="started")
    
    # 1. Inicializa o banco de dados
    database.inicializar_banco()

    # 2. Busca as tarefas pendentes
    solicitacoes_pendentes = database.obter_solicitacoes_pendentes()
    if not solicitacoes_pendentes:
        print("✅ Nenhuma solicitação pendente encontrada. Trabalho concluído!")
        log_event(logger, "Robo de detalhes finalizado sem pendencias.", status="success")
        push_robot_metrics("robo-detalhes", "success", duration_seconds=time.monotonic() - inicio, successes=0, failures=0)
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
        max_tentativas = int(os.getenv("RPA_DETALHES_MAX_TENTATIVAS", "3"))
        espera_segundos = int(os.getenv("RPA_DETALHES_ESPERA_RETRY_SEGUNDOS", "10"))
        sucessos = 0
        falhas = 0
        for i, numero in enumerate(solicitacoes_pendentes):
            print(f"\n[🔄] Processando {i+1}/{total}: {numero}")
            if processar_com_retentativas(portal_page, numero, max_tentativas, espera_segundos):
                sucessos += 1
                print(f"✅ Dados de {numero} atualizados com sucesso!")
            else:
                falhas += 1
        
        print("\n🏁 Fim da coleta de dados detalhados.")
        status = "success" if falhas == 0 else "partial_failure"
        log_event(
            logger,
            f"Execucao do robo de detalhes finalizada. sucessos={sucessos} falhas={falhas} duracao_s={time.monotonic() - inicio:.1f}",
            status=status,
        )
        push_robot_metrics(
            "robo-detalhes",
            status,
            duration_seconds=time.monotonic() - inicio,
            successes=sucessos,
            failures=falhas,
        )

    except Exception as e:
        print(f"\n========================= ERRO CRÍTICO =========================")
        print(f"Ocorreu uma falha na automação: {e}")
        print(f"================================================================")
        log_event(logger, f"Erro critico no robo de detalhes: {e}", status="critical_error")
        push_robot_metrics("robo-detalhes", "critical_error", duration_seconds=time.monotonic() - inicio)
    finally:
        # 6. Fecha o navegador
        print("\n... Fechando o navegador e encerrando o script ...")
        nav.fechar()

if __name__ == "__main__":
    run()
