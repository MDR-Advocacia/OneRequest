import schedule
import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from RPA.observability import install_print_logger, log_event

PROJECT_DIR = Path(__file__).resolve().parent
PYTHON_EXE = sys.executable
logger = install_print_logger("agendador-mestre")


def executar_robo_1():
    """Executa o Robô 1: Coleta de Números de Solicitação."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- INICIANDO ROBO 1: Coleta de Numeros ---")
    log_event(logger, "Iniciando robo 1.", robot="robo-coleta-numeros", status="started")
    try:
        # Chama o script do Robô 1
        subprocess.run(
            [PYTHON_EXE, str(PROJECT_DIR / "RPA" / "coletaDadosNumeroSolicitacoes.py")],
            check=True,
            cwd=PROJECT_DIR
        )
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- ROBO 1 FINALIZADO COM SUCESSO ---")
        log_event(logger, "Robo 1 finalizado com sucesso.", robot="robo-coleta-numeros", status="success")
        return True # Retorna sucesso
    except Exception as e:
        print(f"\n!!!!!! ERRO CRITICO NA EXECUCAO DO ROBO 1: {e} !!!!!!")
        log_event(logger, f"Erro critico na execucao do robo 1: {e}", robot="robo-coleta-numeros", status="error")
        return False # Retorna falha

def executar_robo_2():
    """Executa o Robô 2: Coleta de Detalhes das Solicitações."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- INICIANDO ROBO 2: Coleta de Detalhes ---")
    log_event(logger, "Iniciando robo 2.", robot="robo-detalhes", status="started")
    try:
        # Chama o script do Robô 2
        subprocess.run(
            [PYTHON_EXE, str(PROJECT_DIR / "RPA" / "main.py")],
            check=True,
            cwd=PROJECT_DIR
        )
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- ROBO 2 FINALIZADO COM SUCESSO ---")
        log_event(logger, "Robo 2 finalizado com sucesso.", robot="robo-detalhes", status="success")
    except Exception as e:
        print(f"\n!!!!!! ERRO CRITICO NA EXECUCAO DO ROBO 2: {e} !!!!!!")
        log_event(logger, f"Erro critico na execucao do robo 2: {e}", robot="robo-detalhes", status="error")

def ciclo_completo_de_automacao():
    """
    Orquestra a execução sequencial dos robôs com um intervalo.
    """
    # Executa o Robô 1
    sucesso_robo_1 = executar_robo_1()

    # Apenas continua para o Robô 2 se o Robô 1 foi bem-sucedido
    if sucesso_robo_1:
        print("\n---------------------------------------------------------")
        print("[⏳] Aguardando 20 s antes de iniciar o Robô 2...")
        print("---------------------------------------------------------")
        time.sleep(20) # Pausa de 20 segundos (20 segundos)
        
        # Executa o Robô 2
        executar_robo_2()
    else:
        print("\n[⚠️] O Robô 2 não será executado devido a uma falha no Robô 1.")

    proxima_execucao = schedule.jobs[0].next_run.strftime('%H:%M:%S') if schedule.jobs else 'N/A'
    print(f"\n=========================================================")
    print(f"   CICLO DE AUTOMACAO FINALIZADO.    ")
    print(f"   Próxima execução agendada para as {proxima_execucao}.")
    print(f"=========================================================")


# --- AGENDAMENTO ---
# Agende a execução do ciclo completo a cada 1 hora.
schedule.every(1).hour.do(ciclo_completo_de_automacao)

print(">>> AGENDADOR MESTRE INICIADO <<<")
print("Iniciando o primeiro ciclo de automação agora...")

# Executa o ciclo uma vez imediatamente ao iniciar
ciclo_completo_de_automacao()

while True:
    schedule.run_pending()
    time.sleep(1) # Verifica a cada segundo se há uma tarefa agendada para rodar
