import subprocess
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BAT_FILE_PATH = Path(__file__).resolve().parent / "abrir_chrome.bat"
CDP_ENDPOINT = "http://localhost:9222"

class Navegador:
    def __init__(self):
        self.browser_process = None
        self.p = None
        self.browser = None
        self.context = None
        self.page = None

    def iniciar(self):
        """Abre o navegador Chrome com a porta de depuração."""
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
        """Fecha o processo do navegador e a instância do Playwright."""
        if self.p:
            self.p.stop()
        if self.browser_process:
            print("    Fechando navegador...")
            subprocess.run(f"TASKKILL /F /PID {self.browser_process.pid} /T", shell=True, capture_output=True)
            print("🏁 Navegador fechado.")