import schedule
import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from RPA.observability import install_print_logger, log_event

PROJECT_DIR = Path(__file__).resolve().parent
PYTHON_EXE = sys.executable
logger = install_print_logger("scheduler-coleta-numeros")


def executar_robo_coleta_numeros():
    """Executa o robô que coleta os números de solicitação."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- INICIANDO ROBO 1: Coleta de Numeros ---")
    log_event(logger, "Iniciando robo de coleta de numeros.", robot="robo-coleta-numeros", status="started")
    try:
        subprocess.run(
            [PYTHON_EXE, str(PROJECT_DIR / "RPA" / "coletaDadosNumeroSolicitacoes.py")],
            check=True,
            cwd=PROJECT_DIR
        )
        log_event(logger, "Robo de coleta de numeros finalizado com sucesso.", robot="robo-coleta-numeros", status="success")
    except Exception as e:
        print(f"\n!!!!!! ERRO CRITICO NA EXECUCAO DO ROBO 1: {e} !!!!!!")
        log_event(logger, f"Erro critico na execucao do robo de coleta de numeros: {e}", robot="robo-coleta-numeros", status="error")
    
    proxima = schedule.jobs[0].next_run.strftime('%H:%M:%S') if schedule.jobs else 'N/A'
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- ROBO 1 FINALIZADO. Proxima execucao as {proxima} ---")

# Agendamento: A cada 1 hora.
schedule.every(1).hour.do(executar_robo_coleta_numeros)

print(">>> Agendador do ROBO 1 (Coleta de Numeros) Iniciado. Primeira execucao agora...")
executar_robo_coleta_numeros()

while True:
    schedule.run_pending()
    time.sleep(60)
