import schedule
import time
import subprocess
from datetime import datetime

def executar_robos():
    """
    Função que executa os dois robôs de RPA em sequência.
    """
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- INICIANDO CICLO DE EXECUCAO DOS ROBOS ---")
    
    try:
        # --- ETAPA 1: Coletar os números de solicitação ---
        print("\n[ROBO 1] Executando coletaDadosNumeroSolicitacoes.py...")
        # Usamos subprocess.run para chamar o script e esperar ele terminar.
        # O 'shell=True' pode ser necessário dependendo da configuração do seu sistema.
        # O 'capture_output=True' e 'text=True' nos ajuda a ver o que o script imprimiu.
        resultado_robo1 = subprocess.run(
            ["python", "RPA/coletaDadosNumeroSolicitacoes.py"],
            capture_output=True, text=True, check=True, shell=True
        )
        print("[ROBO 1] Saida:")
        print(resultado_robo1.stdout)
        if resultado_robo1.stderr:
            print("[ROBO 1] Erros:")
            print(resultado_robo1.stderr)
        print("[ROBO 1] Coleta de numeros finalizada com sucesso!")

        # --- ETAPA 2: Detalhar as solicitações pendentes ---
        print("\n[ROBO 2] Executando main.py para detalhar as pendencias...")
        resultado_robo2 = subprocess.run(
            ["python", "RPA/main.py"],
            capture_output=True, text=True, check=True, shell=True
        )
        print("[ROBO 2] Saida:")
        print(resultado_robo2.stdout)
        if resultado_robo2.stderr:
            print("[ROBO 2] Erros:")
            print(resultado_robo2.stderr)
        print("[ROBO 2] Detalhamento finalizado com sucesso!")

    except subprocess.CalledProcessError as e:
        print("\n!!!!!! ERRO CRITICO DURANTE A EXECUCAO DE UM ROBO !!!!!!")
        print(f"O script '{e.cmd}' falhou com o codigo de saida {e.returncode}.")
        print("--- SAIDA PADRAO ---")
        print(e.stdout)
        print("--- SAIDA DE ERRO ---")
        print(e.stderr)
    except Exception as e:
        print(f"\n!!!!!! OCORREU UM ERRO INESPERADO NO AGENDADOR: {e} !!!!!!")
        
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- CICLO DE EXECUCAO FINALIZADO ---")


# --- CONFIGURAÇÃO DO AGENDAMENTO ---
# Defina aqui os horários que você quer que os robôs executem.
# Exemplos:
schedule.every().day.at("08:00").do(executar_robos)
schedule.every().day.at("14:00").do(executar_robos)
# schedule.every(4).hours.do(executar_robos) # A cada 4 horas
# schedule.every(30).minutes.do(executar_robos) # A cada 30 minutos (para testes)

print(">>> Agendador de Robos Iniciado <<<")
print("Executando a primeira vez agora para garantir que tudo esta funcionando...")
executar_robos()

# Define o agendamento para rodar todo dia às 08:00 da manhã
print("Proxima execucao agendada para as 08:00. Depois roda as 14:00 todos os dias.")

while True:
    # Verifica a cada minuto se há uma tarefa agendada para ser executada
    schedule.run_pending()
    time.sleep(60)