import time
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

# --- CONFIGURAÇÕES OBRIGATÓRIAS ---

# 1. URL da sua extensão.
EXTENSION_URL = "chrome-extension://lnidijeaekolpfeckelhkomndglcglhh/index.html"

# 2. Nome exato do seu arquivo .bat.
BAT_FILE_PATH = Path(__file__).resolve().parent / "abrir_chrome.bat"

# 3. Porta de depuração.
CDP_ENDPOINT = "http://localhost:9222"

def main():
    """
    Função principal que orquestra toda a automação, do início ao fim.
    """
    browser_process = None
    try:
        # ETAPA 1: Iniciar o Navegador via .bat
        print(f"▶️  Executando o script: {BAT_FILE_PATH}")
        browser_process = subprocess.Popen(
            str(BAT_FILE_PATH), 
            shell=True, 
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
        print("    Aguardando o navegador iniciar...")
        
        with sync_playwright() as p:
            browser = None
            # ETAPA 2: Conectar ao Navegador Aberto
            for attempt in range(15): # Tenta se conectar por até 30 segundos
                try:
                    time.sleep(2)
                    print(f"    Tentativa de conexão nº {attempt + 1}...")
                    browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
                    print("✅ Conectado com sucesso ao navegador!")
                    break 
                except Exception:
                    continue
            
            if not browser:
                raise ConnectionError("Não foi possível conectar ao navegador.")

            context = browser.contexts[0]
            
            # ETAPA 3: Abrir a Extensão, Pesquisar e Realizar o Login
            print(f"🚀 Navegando diretamente para a URL da extensão...")
            extension_page = context.new_page()
            extension_page.goto(EXTENSION_URL)
            extension_page.wait_for_load_state("domcontentloaded")

            print("    - Localizando o campo de busca na extensão...")
            search_input = extension_page.get_by_placeholder("Digite ou selecione um sistema pra acessar")
            search_input.wait_for(state="visible", timeout=5000)

            print("    - Pesquisando por 'banco do'...")
            search_input.fill("banco do")

            print("🖱️  Clicando no item de menu 'Banco do Brasil - Intranet'...")
            login_button = extension_page.locator(
                'div[role="menuitem"]:not([disabled])', 
                has_text="Banco do Brasil - Intranet"
            ).first
            login_button.click(timeout=10000)

            # --- LINHA ADICIONADA ---
            # Clica no botão "ACESSAR" que aparece após a seleção.
            print("    - Clicando no botão de confirmação 'ACESSAR'...")
            extension_page.get_by_role("button", name="ACESSAR").click(timeout=5000)
            # --------------------------

            print("✔️  Login confirmado! Aguardando 5 segundos para a autenticação se propagar.")
            time.sleep(5)
            extension_page.close()
            
            print("\n✅ PROCESSO DE LOGIN FINALIZADO. O robô pode continuar.")
            
    except Exception as e:
        print("\n========================= ERRO =========================")
        print(f"Ocorreu uma falha na automação: {e}")
        print("========================================================")
    finally:
        # ETAPA 5: Finalização Limpa
        if browser_process:
            input("\n... Pressione Enter para fechar o navegador e encerrar o script ...")
            subprocess.run(f"TASKKILL /F /PID {browser_process.pid} /T", shell=True, capture_output=True)
            print("🏁 Navegador fechado. Fim da execução.")

if __name__ == "__main__":
    main()