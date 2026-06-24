import sys
import os
import time
from navegador import Navegador
import portal_bb
from observability import install_print_logger, log_event, push_robot_metrics

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))

from RPA import api_client as database

logger = install_print_logger("robo-detalhes")


def _fechar_paginas_extras(portal_page):
    """Fecha popups/abas remanescentes, mantendo apenas a aba principal do portal."""
    for page in list(portal_page.context.pages):
        if page != portal_page:
            try:
                page.close()
            except Exception:
                pass


def _marcar_acesso_negado(numero):
    """Registra a solicitacao como 'Acesso nao autorizado' para sair da fila de pendentes."""
    database.atualizar_detalhes_solicitacao({
        "numero_solicitacao": numero,
        "titulo": "Acesso não autorizado",
        "npj_direcionador": "",
        "prazo": "",
        "texto_dmi": "Advogado terceirizado não cadastrado no portal. Contatar a Ajure de relacionamento.",
        "numero_processo": "Acesso não autorizado",
        "polo": "N/A",
    })


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
        except portal_bb.AcessoNaoAutorizadoError as exc:
            # Erro permanente: repetir nao resolve. Marca, registra e segue para a proxima.
            print(f"⛔ {numero}: acesso não autorizado (advogado não cadastrado no portal). Marcando e seguindo.")
            log_event(
                logger,
                f"Acesso não autorizado para a solicitacao: {exc}",
                solicitacao=numero,
                attempt=tentativa,
                status="skipped",
            )
            try:
                _marcar_acesso_negado(numero)
            except Exception as db_exc:
                print(f"    ⚠️ Falha ao marcar acesso negado de {numero}: {db_exc}")
            _fechar_paginas_extras(portal_page)
            return False
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
                _fechar_paginas_extras(portal_page)
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
