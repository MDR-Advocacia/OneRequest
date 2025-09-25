import schedule
import time
import subprocess
from datetime import datetime

def executar_robo_detalhes():
    """Executa o robô que busca os detalhes das solicitações."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- INICIANDO ROBO 2: Detalhamento de Solicitacoes ---")
    try:
        subprocess.run(
            ["python", "RPA/main.py"],
            check=True, shell=True
        )
    except Exception as e:
        print(f"\n!!!!!! ERRO CRITICO NA EXECUCAO DO ROBO 2: {e} !!!!!!")

    proxima = schedule.jobs[0].next_run.strftime('%H:%M:%S') if schedule.jobs else 'N/A'
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- ROBO 2 FINALIZADO. Proxima execucao as {proxima} ---")

# Agendamento: A cada 2 horas.
schedule.every(2).hours.do(executar_robo_detalhes)

print(">>> Agendador do ROBO 2 (Detalhamento) Iniciado. Primeira execucao agora...")
executar_robo_detalhes()

while True:
    schedule.run_pending()
    time.sleep(60)