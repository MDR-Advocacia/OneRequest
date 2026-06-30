import schedule
import time
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from RPA.observability import install_print_logger, log_event

PROJECT_DIR = Path(__file__).resolve().parent
PYTHON_EXE = sys.executable
logger = install_print_logger("scheduler-status-dia")

# Janela de execucao (horario local de Brasilia). Roda de hora em hora nesse intervalo.
HORA_INICIO = int(os.getenv("RPA_STATUS_HORA_INICIO", "12"))  # a partir do meio-dia
HORA_FIM = int(os.getenv("RPA_STATUS_HORA_FIM", "18"))


def executar_robo_status():
    """Executa o robo que atualiza o status do portal das solicitacoes que vencem hoje."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- INICIANDO ROBO Status do Dia ---")
    log_event(logger, "Iniciando robo de status do dia.", robot="robo-status-dia", status="started")
    try:
        subprocess.run(
            [PYTHON_EXE, str(PROJECT_DIR / "RPA" / "coletaStatusDia.py")],
            check=True,
            cwd=PROJECT_DIR,
        )
        log_event(logger, "Robo de status do dia finalizado com sucesso.", robot="robo-status-dia", status="success")
    except Exception as e:
        print(f"\n!!!!!! ERRO CRITICO NA EXECUCAO DO ROBO Status do Dia: {e} !!!!!!")
        log_event(logger, f"Erro critico na execucao do robo de status do dia: {e}", robot="robo-status-dia", status="error")

    proxima = min((j.next_run for j in schedule.jobs), default=None)
    proxima_txt = proxima.strftime('%d/%m %H:%M:%S') if proxima else 'N/A'
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- Status do Dia FINALIZADO. Proxima execucao: {proxima_txt} ---")


# Agendamento: de hora em hora, das HORA_INICIO ate HORA_FIM (horario local).
for h in range(HORA_INICIO, HORA_FIM + 1):
    schedule.every().day.at(f"{h:02d}:00").do(executar_robo_status)

print(f">>> Agendador 'Status do Dia' iniciado (das {HORA_INICIO}h as {HORA_FIM}h, de hora em hora).")

# Roda imediatamente apenas se ja passou do horario de inicio.
if datetime.now().hour >= HORA_INICIO:
    print("Ja passou do horario de inicio - executando agora...")
    executar_robo_status()
else:
    print(f"Antes das {HORA_INICIO}h - aguardando a primeira execucao agendada.")

while True:
    schedule.run_pending()
    time.sleep(60)
