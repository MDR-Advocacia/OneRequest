import os
import subprocess
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

from lock_chrome import LockChrome, matar_chrome_robo

BAT_FILE_PATH = Path(__file__).resolve().parent / "abrir_chrome.bat"
CDP_ENDPOINT = "http://localhost:9222"


def _modo_headless():
    return os.getenv("RPA_HEADLESS", "0").strip().lower() in ("1", "true", "sim", "yes", "on")


class Navegador:
    def __init__(self):
        self.browser_process = None
        self.p = None
        self.browser = None
        self.context = None
        self.page = None
        self._lock = None
        self._headless = _modo_headless()

    def iniciar(self):
        if self._headless:
            return self._iniciar_headless()
        return self._iniciar_cdp()

    def _iniciar_headless(self):
        """Lança Chromium headless via Playwright (Docker / Linux server)."""
        print("▶️  Iniciando Chromium headless (Playwright)...")
        self._lock = LockChrome()
        self._lock.acquire()

        self.p = sync_playwright().start()
        self.browser = self.p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
            ],
        )
        self.context = self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        print("✅ Chromium headless pronto.")
        return True

    def _iniciar_cdp(self):
        """Abre Chrome via .bat e conecta por CDP (Windows local)."""
        self._lock = LockChrome()
        self._lock.acquire()
        print(f"▶️  Executando o script: {BAT_FILE_PATH}")
        self.browser_process = subprocess.Popen(
            str(BAT_FILE_PATH),
            shell=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
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
        print("\n... Iniciando rotina de fechamento do navegador ...")
        try:
            if self.context and self._headless:
                try:
                    self.context.close()
                except Exception:
                    pass

            if self.browser:
                try:
                    if self._headless:
                        self.browser.close()
                    elif self.browser.is_connected():
                        self.browser.close()
                    print("     Conexão do Playwright fechada.")
                except Exception as e:
                    print(f"     Aviso: Erro ao fechar conexão Playwright: {e}")

            if self.p:
                try:
                    self.p.stop()
                    print("     Instância do Playwright (p) parada.")
                except Exception as e:
                    print(f"     Aviso: Erro ao parar 'p': {e}")

            if not self._headless:
                print("     Encerrando o Chrome do robô (todos os processos do perfil)...")
                matar_chrome_robo()
        finally:
            if getattr(self, "_lock", None):
                self._lock.release()
                self._lock = None

        print("--- Rotina de fechamento concluída ---")
