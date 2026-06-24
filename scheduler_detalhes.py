import schedule
import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from RPA.observability import install_print_logger, log_event

PROJECT_DIR = Path(__file__).resolve().parent
PYTHON_EXE = sys.executable
logger = install_print_logger("scheduler-detalhes")


def executar_robo_detalhes():
    """Executa o robô que busca os detalhes das solicitações."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- INICIANDO ROBO 2: Detalhamento de Solicitacoes ---")
    log_event(logger, "Iniciando robo de detalhes.", robot="robo-detalhes", status="started")
    try:
        subprocess.run(
            [PYTHON_EXE, str(PROJECT_DIR / "RPA" / "main.py")],
            check=True,
            cwd=PROJECT_DIR
        )
        log_event(logger, "Robo de detalhes finalizado com sucesso.", robot="robo-detalhes", status="success")
    except Exception as e:
        print(f"\n!!!!!! ERRO CRITICO NA EXECUCAO DO ROBO 2: {e} !!!!!!")
        log_event(logger, f"Erro critico na execucao do robo de detalhes: {e}", robot="robo-detalhes", status="error")

    proxima = schedule.jobs[0].next_run.strftime('%H:%M:%S') if schedule.jobs else 'N/A'
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- ROBO 2 FINALIZADO. Proxima execucao as {proxima} ---")

# Agendamento: A cada 2 horas.
schedule.every(2).hours.do(executar_robo_detalhes)

print(">>> Agendador do ROBO 2 (Detalhamento) Iniciado. Primeira execucao agora...")
executar_robo_detalhes()

while True:
    schedule.run_pending()
    time.sleep(60)
