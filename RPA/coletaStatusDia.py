"""Robo 'Status do Dia': atualiza o status do portal das solicitacoes que VENCEM HOJE ou estao ATRASADAS.

A cada execucao:
  1. Pega as solicitacoes abertas com prazo <= hoje (via API /solicitacoes/vencem-hoje).
  2. Acessa cada uma na buscaRapida.seam e le o 'Status da solicitacao' (span.status_texto).
  3. Grava em status_portal (via API /solicitacoes/status-portal).
  4. SO nas atrasadas (prazo ja vencido, via API /solicitacoes/atrasadas): verifica se
     ha anotacao no portal do BB e grava em tem_anotacao_portal (Sim/Nao). As que vencem
     hoje nao passam por essa verificacao.

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


def _rotulo_anotacao(tem_anotacao):
    """Converte o booleano da verificacao em rotulo para o banco (ou None se nao verificado)."""
    if tem_anotacao is True:
        return "Sim"
    if tem_anotacao is False:
        return "Não"
    return None  # desconhecido -> nao sobrescreve o valor atual


def processar_com_retentativas(portal_page, numero, max_tentativas, espera_segundos,
                               verificar_anotacao=False):
    ultimo_erro = None
    for tentativa in range(1, max_tentativas + 1):
        try:
            if tentativa > 1:
                print(f"    - Nova tentativa {tentativa}/{max_tentativas} para {numero}...")
            if verificar_anotacao:
                # Atrasadas: coleta status E verifica se ha anotacao no portal.
                status, tem_anotacao = portal_bb.coletar_status_e_anotacao_portal(portal_page, numero)
                rotulo_anotacao = _rotulo_anotacao(tem_anotacao)
            else:
                # Vence hoje (ainda nao atrasada): so coleta o status, sem tocar na anotacao.
                status = portal_bb.coletar_status_portal(portal_page, numero)
                rotulo_anotacao = None
            database.atualizar_status_portal(numero, status, tem_anotacao_portal=rotulo_anotacao)
            if verificar_anotacao:
                anotacao_txt = rotulo_anotacao if rotulo_anotacao is not None else "não verificado"
            else:
                anotacao_txt = "não aplicável (vence hoje)"
            print(f"✅ {numero}: status do portal = '{status}' | anotação no portal = {anotacao_txt}")
            log_event(logger, "Status do portal atualizado.", solicitacao=numero,
                      attempt=tentativa, status="success", status_portal=status,
                      tem_anotacao_portal=rotulo_anotacao)
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
        print("✅ Nenhuma solicitação vencendo hoje ou atrasada. Nada a atualizar.")
        log_event(logger, "Robo de status do dia finalizado sem itens.", status="success")
        push_robot_metrics("robo-status-dia", "success", duration_seconds=time.monotonic() - inicio, successes=0, failures=0)
        return
    # A verificacao de anotacao do portal roda SO nas atrasadas (prazo ja vencido);
    # as que vencem hoje tem apenas o status coletado. Se o endpoint /atrasadas ainda
    # nao estiver no ar (ex.: servidor sem o redeploy), degrada com seguranca: pula a
    # verificacao de anotacao neste ciclo em vez de derrubar o robo.
    try:
        atrasadas = set(database.obter_solicitacoes_atrasadas())
    except Exception as exc:
        atrasadas = set()
        print(f"⚠️ Não foi possível obter a lista de atrasadas ({exc}). "
              f"Verificação de anotação será pulada neste ciclo.")
        log_event(logger, f"Falha ao obter atrasadas; anotacao pulada: {exc}", status="warning")
    print(f"📂 {len(vencem_hoje)} solicitações para atualizar o status "
          f"({len(atrasadas)} atrasadas com verificação de anotação + "
          f"{len(vencem_hoje) - len(atrasadas)} vencendo hoje).")

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
            eh_atrasada = numero in atrasadas
            marcador = "atrasada" if eh_atrasada else "vence hoje"
            print(f"\n[🔄] Processando {i+1}/{total}: {numero} ({marcador})")
            if processar_com_retentativas(portal_page, numero, max_tentativas, espera_segundos,
                                          verificar_anotacao=eh_atrasada):
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
