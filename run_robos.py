import schedule
import time
import subprocess
from datetime import datetime

def executar_robo_1():
    """Executa o Robô 1: Coleta de Números de Solicitação."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- INICIANDO ROBO 1: Coleta de Numeros ---")
    try:
        # Chama o script do Robô 1
        subprocess.run(
            ["python", "RPA/coletaDadosNumeroSolicitacoes.py"],
            check=True,
            shell=True
        )
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- ROBO 1 FINALIZADO COM SUCESSO ---")
        return True # Retorna sucesso
    except Exception as e:
        print(f"\n!!!!!! ERRO CRITICO NA EXECUCAO DO ROBO 1: {e} !!!!!!")
        return False # Retorna falha

def executar_robo_2():
    """Executa o Robô 2: Coleta de Detalhes das Solicitações."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- INICIANDO ROBO 2: Coleta de Detalhes ---")
    try:
        # Chama o script do Robô 2
        subprocess.run(
            ["python", "RPA/main.py"],
            check=True,
            shell=True
        )
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- ROBO 2 FINALIZADO COM SUCESSO ---")
    except Exception as e:
        print(f"\n!!!!!! ERRO CRITICO NA EXECUCAO DO ROBO 2: {e} !!!!!!")

def ciclo_completo_de_automacao():
    """
    Orquestra a execução sequencial dos robôs com um intervalo.
    """
    # Executa o Robô 1
    sucesso_robo_1 = executar_robo_1()

    # Apenas continua para o Robô 2 se o Robô 1 foi bem-sucedido
    if sucesso_robo_1:
        print("\n---------------------------------------------------------")
        print("[⏳] Aguardando 2 minutos antes de iniciar o Robô 2...")
        print("---------------------------------------------------------")
        time.sleep(120) # Pausa de 120 segundos (2 minutos)
        
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