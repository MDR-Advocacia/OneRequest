"""Robo 'Status do Dia': atualiza o status do portal das solicitacoes que VENCEM HOJE.

A cada execucao:
  1. Pega as solicitacoes abertas com prazo = hoje (via API /solicitacoes/vencem-hoje).
  2. Acessa cada uma na buscaRapida.seam e le o 'Status da solicitacao' (span.status_texto).
  3. Grava em status_portal (via API /solicitacoes/status-portal).

Roda localmente (Chrome/Playwright) e fala com a producao pela API REST.
"""
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

logger = install_print_logger("robo-status-dia")


def _fechar_paginas_extras(portal_page):
    for page in list(portal_page.context.pages):
        if page != portal_page:
            try:
                page.close()
            except Exception:
                pass


def processar_com_retentativas(portal_page, numero, max_tentativas, espera_segundos):
    ultimo_erro = None
    for tentativa in range(1, max_tentativas + 1):
        try:
            if tentativa > 1:
                print(f"    - Nova tentativa {tentativa}/{max_tentativas} para {numero}...")
            status = portal_bb.coletar_status_portal(portal_page, numero)
            database.atualizar_status_portal(numero, status)
            print(f"✅ {numero}: status do portal = '{status}'")
            log_event(logger, "Status do portal atualizado.", solicitacao=numero,
                      attempt=tentativa, status="success", status_portal=status)
            return True
        except portal_bb.AcessoNaoAutorizadoError as exc:
            # Erro permanente para esta solicitacao: registra e segue.
            print(f"⛔ {numero}: acesso não autorizado. Marcando status e seguindo.")
            log_event(logger, f"Acesso não autorizado: {exc}", solicitacao=numero,
                      attempt=tentativa, status="skipped")
            try:
                database.atualizar_status_portal(numero, "Acesso não autorizado")
            except Exception as db_exc:
                print(f"    ⚠️ Falha ao gravar status de {numero}: {db_exc}")
            _fechar_paginas_extras(portal_page)
            return False
        except Exception as exc:
            ultimo_erro = exc
            log_event(logger, f"Falha ao coletar status: {exc}", solicitacao=numero,
                      attempt=tentativa, status="error")
            if tentativa < max_tentativas:
                print(f"⚠️ Tentativa {tentativa}/{max_tentativas} falhou para {numero}: {exc}")
                print(f"    - Aguardando {espera_segundos}s antes de tentar novamente...")
                _fechar_paginas_extras(portal_page)
                time.sleep(espera_segundos)
                continue
            print(f"❌ Erro ao processar {numero} após {max_tentativas} tentativas: {ultimo_erro}")
            return False


def run():
    inicio = time.monotonic()
    log_event(logger, "Execucao do robo de status do dia iniciada.", status="started")

    database.inicializar_banco()

    vencem_hoje = database.obter_solicitacoes_vencem_hoje()
    if not vencem_hoje:
        print("✅ Nenhuma solicitação vencendo hoje. Nada a atualizar.")
        log_event(logger, "Robo de status do dia finalizado sem itens.", status="success")
        push_robot_metrics("robo-status-dia", "success", duration_seconds=time.monotonic() - inicio, successes=0, failures=0)
        return
    print(f"📂 {len(vencem_hoje)} solicitações vencendo hoje para atualizar o status.")

    nav = Navegador()
    try:
        nav.iniciar()
        portal_page = portal_bb.fazer_login(nav.context)

        total = len(vencem_hoje)
        max_tentativas = int(os.getenv("RPA_STATUS_MAX_TENTATIVAS", "3"))
        espera_segundos = int(os.getenv("RPA_STATUS_ESPERA_RETRY_SEGUNDOS", "10"))
        sucessos = 0
        falhas = 0
        for i, numero in enumerate(vencem_hoje):
            print(f"\n[🔄] Processando {i+1}/{total}: {numero}")
            if processar_com_retentativas(portal_page, numero, max_tentativas, espera_segundos):
                sucessos += 1
            else:
                falhas += 1

        print("\n🏁 Fim da coleta de status do dia.")
        status = "success" if falhas == 0 else "partial_failure"
        log_event(logger, f"Execucao do robo de status do dia finalizada. sucessos={sucessos} falhas={falhas} duracao_s={time.monotonic() - inicio:.1f}", status=status)
        push_robot_metrics("robo-status-dia", status, duration_seconds=time.monotonic() - inicio, successes=sucessos, failures=falhas)

    except Exception as e:
        print(f"\n========================= ERRO CRÍTICO =========================")
        print(f"Ocorreu uma falha na automação: {e}")
        print(f"================================================================")
        log_event(logger, f"Erro critico no robo de status do dia: {e}", status="critical_error")
        push_robot_metrics("robo-status-dia", "critical_error", duration_seconds=time.monotonic() - inicio)
    finally:
        print("\n... Fechando o navegador e encerrando o script ...")
        nav.fechar()


if __name__ == "__main__":
    run()
