import subprocess
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
import sys  # Necessário para checar o sistema (win32)
import re   # Necessário para extrair o PID da porta

from lock_chrome import LockChrome

BAT_FILE_PATH = Path(__file__).resolve().parent / "abrir_chrome.bat"
CDP_ENDPOINT = "http://localhost:9222"

class Navegador:
    def __init__(self):
        self.browser_process = None
        self.p = None
        self.browser = None
        self.context = None
        self.page = None
        self._lock = None

    def iniciar(self):
        """Abre o navegador Chrome com a porta de depuração."""
        # Uso exclusivo do Chrome: aguarda caso outro robo esteja usando (evita conflito na porta 9222).
        self._lock = LockChrome()
        self._lock.acquire()
        print(f"▶️  Executando o script: {BAT_FILE_PATH}")
        self.browser_process = subprocess.Popen(
            str(BAT_FILE_PATH), 
            shell=True, 
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
        print("    Aguardando o navegador iniciar...")
        
        self.p = sync_playwright().start()
        for attempt in range(15):
            try:
                time.sleep(2)
                print(f"    Tentativa de conexão nº {attempt + 1}...")
                self.browser = self.p.chromium.connect_over_cdp(CDP_ENDPOINT)
                self.context = self.browser.contexts[0]
                print("✅ Conectado com sucesso ao navegador!")
                return True
            except Exception:
                continue
        raise ConnectionError("Não foi possível conectar ao navegador.")

    def fechar(self):
        """
        Fecha o browser, o processo do navegador e a instância do Playwright.
        Esta versão localiza e mata o processo pela porta de depuração (9222),
        pois o PID original (do .bat) não é mais válido.
        """
        print("\n... Iniciando rotina de fechamento do navegador ...")

        try:
            # 1. Desconecta o Playwright do browser
            if self.browser and self.browser.is_connected():
                try:
                    self.browser.close()
                    print("     Conexão do Playwright fechada.")
                except Exception as e:
                    print(f"     Aviso: Erro ao fechar conexão Playwright: {e}")

            # 2. Para a instância principal do Playwright
            if self.p:
                try:
                    self.p.stop()
                    print("     Instância do Playwright (p) parada.")
                except Exception as e:
                    print(f"     Aviso: Erro ao parar 'p': {e}")

            # 3. MATA O PROCESSO DO CHROME PELA PORTA 9222 (A Solução)
            print("     Procurando e finalizando o processo do Chrome na porta 9222...")
            try:
                if sys.platform == "win32":
                    cmd_find_pid = "netstat -ano -p TCP | findstr :9222"
                    result = subprocess.run(cmd_find_pid, shell=True, capture_output=True, text=True, check=False)
                    output = result.stdout.strip()

                    if not output:
                        print("     Nenhum processo encontrado na porta 9222. O navegador pode já estar fechado.")
                    else:
                        pid_match = re.search(r'(\d+)$', output.splitlines()[0])
                        if pid_match:
                            pid = pid_match.group(1)
                            print(f"     Encontrado processo (PID: {pid}) na porta 9222. Finalizando...")
                            subprocess.run(f"TASKKILL /F /PID {pid} /T", shell=True, check=False, capture_output=True)
                            print(f"🏁 Processo {pid} (Chrome) finalizado.")
                        else:
                            print(f"     Não foi possível extrair o PID da saída do netstat: {output}")
                else:
                    subprocess.run("lsof -t -i:9222 | xargs kill -9", shell=True, check=False, capture_output=True)
                    print("     Comando de finalização (Linux/Mac) executado.")
            except Exception as e_kill:
                print(f"     Aviso: Falha ao tentar finalizar o processo da porta 9222: {e_kill}")
        finally:
            # Libera o lock para o proximo robo, sempre.
            if getattr(self, "_lock", None):
                self._lock.release()
                self._lock = None

        print("--- Rotina de fechamento concluída ---")