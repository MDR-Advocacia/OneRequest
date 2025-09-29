import schedule
import time
import subprocess
from datetime import datetime

def executar_robo_coleta_numeros():
    """Executa o robô que coleta os números de solicitação."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- INICIANDO ROBO 1: Coleta de Numeros ---")
    try:
        subprocess.run(
            ["python", "RPA/coletaDadosNumeroSolicitacoes.py"],
            check=True, shell=True
        )
    except Exception as e:
        print(f"\n!!!!!! ERRO CRITICO NA EXECUCAO DO ROBO 1: {e} !!!!!!")
    
    proxima = schedule.jobs[0].next_run.strftime('%H:%M:%S') if schedule.jobs else 'N/A'
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- ROBO 1 FINALIZADO. Proxima execucao as {proxima} ---")

# Agendamento: A cada 1 hora.
schedule.every(1).hour.do(executar_robo_coleta_numeros)

print(">>> Agendador do ROBO 1 (Coleta de Numeros) Iniciado. Primeira execucao agora...")
executar_robo_coleta_numeros()

while True:
    schedule.run_pending()
    time.sleep(60)