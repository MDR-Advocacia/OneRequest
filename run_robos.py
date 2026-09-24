import time
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta
from RPA.observability import install_print_logger, log_event

PROJECT_DIR = Path(__file__).resolve().parent
PYTHON_EXE = sys.executable
logger = install_print_logger("agendador-mestre")

# --- Janela de operacao (horario local de Brasilia) e ritmo ---
HORA_INICIO = int(os.getenv("RPA_ROBOS_HORA_INICIO", "7"))     # nao roda antes das 7h
HORA_FIM = int(os.getenv("RPA_ROBOS_HORA_FIM", "18"))          # nao roda depois das 18h
RETRY_MIN = int(os.getenv("RPA_ROBOS_RETRY_MINUTOS", "5"))     # em caso de erro, retenta a cada 5 min
INICIO_MIN = HORA_INICIO * 60
FIM_MIN = HORA_FIM * 60


def executar_robo_1():
    """Executa o Robô 1: Coleta de Números de Solicitação. Retorna True em sucesso."""
    print(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] --- INICIANDO ROBO 1: Coleta de Numeros ---")
    log_event(logger, "Iniciando robo 1.", robot="robo-coleta-numeros", status="started")
    try:
        subprocess.run([PYTHON_EXE, str(PROJECT_DIR / "RPA" / "coletaDadosNumeroSolicitacoes.py")],
                       check=True, cwd=PROJECT_DIR)
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] --- ROBO 1 FINALIZADO COM SUCESSO ---")
        log_event(logger, "Robo 1 finalizado com sucesso.", robot="robo-coleta-numeros", status="success")
        return True
    except Exception as e:
        print(f"\n!!!!!! ERRO CRITICO NA EXECUCAO DO ROBO 1: {e} !!!!!!")
        log_event(logger, f"Erro critico na execucao do robo 1: {e}", robot="robo-coleta-numeros", status="error")
        return False


def executar_robo_2():
    """Executa o Robô 2: Coleta de Detalhes. Retorna True em sucesso."""
    print(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] --- INICIANDO ROBO 2: Coleta de Detalhes ---")
    log_event(logger, "Iniciando robo 2.", robot="robo-detalhes", status="started")
    try:
        subprocess.run([PYTHON_EXE, str(PROJECT_DIR / "RPA" / "main.py")],
                       check=True, cwd=PROJECT_DIR)
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] --- ROBO 2 FINALIZADO COM SUCESSO ---")
        log_event(logger, "Robo 2 finalizado com sucesso.", robot="robo-detalhes", status="success")
        return True
    except Exception as e:
        print(f"\n!!!!!! ERRO CRITICO NA EXECUCAO DO ROBO 2: {e} !!!!!!")
        log_event(logger, f"Erro critico na execucao do robo 2: {e}", robot="robo-detalhes", status="error")
        return False


def executar_robo_status():
    """Executa o Robô de Status do Dia (status do portal das que vencem hoje/atrasadas). Retorna True em sucesso."""
    print(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] --- INICIANDO ROBO Status do Dia ---")
    log_event(logger, "Iniciando robo status do dia.", robot="robo-status-dia", status="started")
    try:
        subprocess.run([PYTHON_EXE, str(PROJECT_DIR / "RPA" / "coletaStatusDia.py")],
                       check=True, cwd=PROJECT_DIR)
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] --- ROBO Status do Dia FINALIZADO COM SUCESSO ---")
        log_event(logger, "Robo status do dia finalizado com sucesso.", robot="robo-status-dia", status="success")
        return True
    except Exception as e:
        print(f"\n!!!!!! ERRO NA EXECUCAO DO ROBO Status do Dia: {e} !!!!!!")
        log_event(logger, f"Erro na execucao do robo status do dia: {e}", robot="robo-status-dia", status="error")
        return False


def ciclo_completo_de_automacao():
    """Roda, em sequência, Robô 1 (números), Robô 2 (detalhes) e o Robô de Status do Dia.

    O retry do agendador (a cada 5 min em erro) considera apenas Números+Detalhes;
    o Status é best-effort e não força o ciclo a repetir.
    """
    if not executar_robo_1():
        print("\n[⚠️] Robô 2 e Status não serão executados devido a uma falha no Robô 1.")
        return False

    print("\n[⏳] Aguardando 20 s antes de iniciar o Robô 2...")
    time.sleep(20)
    ok_detalhes = executar_robo_2()

    # Robô de Status do Dia — roda em sequência (não simultâneo), best-effort.
    print("\n[⏳] Aguardando 10 s antes de iniciar o Robô de Status...")
    time.sleep(10)
    executar_robo_status()

    return ok_detalhes


# --- Agendamento adaptativo ---

def dentro_janela(dt):
    minutos = dt.hour * 60 + dt.minute
    return INICIO_MIN <= minutos <= FIM_MIN


def clamp_janela(dt):
    """Se dt cair fora da janela [HORA_INICIO, HORA_FIM], empurra para o proximo inicio de janela."""
    minutos = dt.hour * 60 + dt.minute
    if minutos < INICIO_MIN:
        return dt.replace(hour=HORA_INICIO, minute=0, second=0, microsecond=0)
    if minutos > FIM_MIN:
        amanha = dt + timedelta(days=1)
        return amanha.replace(hour=HORA_INICIO, minute=0, second=0, microsecond=0)
    return dt


def topo_proxima_hora(dt):
    return dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def main():
    print(">>> AGENDADOR MESTRE INICIADO <<<")
    print(f"    Janela: {HORA_INICIO}h-{HORA_FIM}h | normal: de hora em hora | em erro: retenta a cada {RETRY_MIN} min.")

    # Primeira execucao: agora, se dentro da janela; senao, no proximo inicio de janela.
    proxima = clamp_janela(datetime.now())
    if dentro_janela(datetime.now()):
        proxima = datetime.now()
    print(f"    Primeira execução prevista: {proxima:%d/%m %H:%M}")

    while True:
        agora = datetime.now()
        if agora >= proxima:
            if dentro_janela(agora):
                sucesso = ciclo_completo_de_automacao()
                fim = datetime.now()
                if sucesso:
                    desejada = topo_proxima_hora(fim)
                    print(f"\n[✅] Ciclo OK. Próxima na hora cheia.")
                else:
                    desejada = fim + timedelta(minutes=RETRY_MIN)
                    print(f"\n[⚠️] Ciclo com erro. Retentando em {RETRY_MIN} min (até dar certo).")
                proxima = clamp_janela(desejada)
            else:
                # Fora da janela (madrugada): agenda para o proximo inicio.
                proxima = clamp_janela(agora)
            print(f"========================================================")
            print(f"   Próxima execução: {proxima:%d/%m %H:%M:%S}")
            print(f"========================================================")
            log_event(logger, f"Proxima execucao agendada para {proxima:%Y-%m-%d %H:%M}", status="scheduled")

        time.sleep(30)


if __name__ == "__main__":
    main()
