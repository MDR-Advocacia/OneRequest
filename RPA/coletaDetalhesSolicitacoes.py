import time
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright, Page
import json
import re

# --- CONFIGURAÇÕES OBRIGATÓRIAS ---

# 1. URL da sua extensão.
EXTENSION_URL = "chrome-extension://lnidijeaekolpfeckelhkomndglcglhh/index.html"

# 2. Nome exato do seu arquivo .bat.
BAT_FILE_PATH = Path(__file__).resolve().parent / "abrir_chrome.bat"

# 3. Porta de depuração.
CDP_ENDPOINT = "http://localhost:9222"

def main():
    """
    Função principal que orquestra a automação para acessar a página detalhada
    de cada número de solicitação.
    """
    browser_process = None
    try:
        print(f"▶️  Executando o script: {BAT_FILE_PATH}")
        browser_process = subprocess.Popen(
            str(BAT_FILE_PATH), 
            shell=True, 
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
        print("    Aguardando o navegador iniciar...")
        
        with sync_playwright() as p:
            browser = None
            for attempt in range(15):
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
            
            print(f"🚀 Navegando diretamente para a URL da extensão...")
            extension_page = context.pages[0] if context.pages else context.new_page()
            extension_page.goto(EXTENSION_URL)
            extension_page.wait_for_load_state("domcontentloaded")

            print("    - Localizando o campo de busca na extensão...")
            search_input = extension_page.get_by_placeholder("Digite ou selecione um sistema pra acessar")
            search_input.wait_for(state="visible", timeout=5000)

            print("    - Pesquisando por 'banco do'...")
            search_input.fill("banco do")

            with context.expect_event('page') as new_page_info:
                print("🖱️  Clicando no item de menu 'Banco do Brasil - Intranet'...")
                login_button = extension_page.locator(
                    'div[role="menuitem"]:not([disabled])', 
                    has_text="Banco do Brasil - Intranet"
                ).first
                login_button.click(timeout=10000)

                print("    - Clicando no botão de confirmação 'ACESSAR'...")
                extension_page.get_by_role("button", name="ACESSAR").click(timeout=5000)
            
            portal_page = new_page_info.value
            extension_page.close()
            
            print("✔️  Login confirmado! Aguardando 5 segundos para a autenticação se propagar.")
            time.sleep(5)
            
            print("    - Navegando para o Portal Jurídico para garantir o carregamento completo...")
            portal_page.goto("https://juridico.bb.com.br/paj/juridico#redirect-completed")
            portal_page.wait_for_selector('p:text("Portal Jurídico")')
            
            print("\n✅ PROCESSO DE LOGIN FINALIZADO. O robô pode continuar.")
            
            print("\n📂 Carregando números de solicitação do arquivo...")
            try:
                with open("numeros_solicitacoes.json", "r", encoding="utf-8") as f:
                    numeros_solicitacoes = json.load(f)
                print(f"✅ {len(numeros_solicitacoes)} números de solicitação encontrados.")
            except FileNotFoundError:
                print("❌ Arquivo 'numeros_solicitacoes.json' não encontrado. Certifique-se de executar o script anterior primeiro.")
                return
            
            dados_detalhados = []
            
            for i, numero_completo_original in enumerate(numeros_solicitacoes[:1]): 
                try:
                    match = re.match(r"(\d{4})\/(\d{10})", numero_completo_original)
                    if not match:
                        print(f"⚠️ Formato de número inválido: {numero_completo_original}. Pulando.")
                        continue
                    
                    ano = match.group(1)
                    numero = match.group(2)
                    
                    print(f"\n[🔄] {i+1}/{len(numeros_solicitacoes)} - Acessando detalhes para o número: {numero_completo_original}")
                    
                    url_detalhada = f"https://juridico.bb.com.br/wfj/paginas/negocio/tarefa/pesquisar/buscaRapida.seam?buscaRapidaProcesso=busca_solicitacoes&anoProcesso=&numeroProcesso=&numeroVariacaoProcesso=&anoProcesso=&numeroProcesso=&numeroVariacaoProcesso=&numeroTombo=&numeroCpf=&numeroCnpj=&nomePessoa=&nomePessoaParte=&nomeFantasia=&nomeFantasiaParte=&anoSolicitacaoBuscaRapida={ano}&numeroSolicitacaoBuscaRapida={numero}&anoOficioBuscaRapida=&numeroOficioBuscaRapida="
                    
                    portal_page.goto(url_detalhada, timeout=60000, wait_until="domcontentloaded")
                    
                    portal_page.wait_for_selector('h2.left:has-text("Solicitação : Detalhamento")', timeout=20000)
                    print("✅ Página de detalhes carregada com sucesso!")
                    
                    # ###############################################################
                    # ## INÍCIO - LÓGICA DE EXTRAÇÃO DE DADOS                      ##
                    # ###############################################################
                    
                    print("    - Extraindo dados da página...")
                    
                    # Extração da primeira div
                    numero_solicitacao_raw = portal_page.locator('span.info_tarefa_label_numero:has-text("Nº da solicitação:") + span.info_tarefa_numero').inner_text()
                    titulo = portal_page.locator('div.left:has(span:has-text("Título:")) span.info_tarefa_label').inner_text()

                    # Extração da segunda div (form_menu)
                    npj_direcionador = portal_page.locator('label.label_padrao:has-text("NPJ Direcionador:") + span span.content').inner_text()
                    prazo = portal_page.locator('label.label_padrao:has-text("Prazo:") + span span.content').inner_text()

                    dados_solicitacao = {
                        "numero_solicitacao": numero_solicitacao_raw.replace("DMI - ", "").strip(),
                        "titulo": titulo.strip(),
                        "npj_direcionador": npj_direcionador.strip(),
                        "prazo": prazo.strip(),
                    }

                    dados_detalhados.append(dados_solicitacao)
                    print(f"    - Dados extraídos: {dados_solicitacao}")
                    
                    # ###############################################################
                    # ## FIM - LÓGICA DE EXTRAÇÃO DE DADOS                         ##
                    # ###############################################################

                    time.sleep(2)
                
                except Exception as e:
                    print(f"\n========================= ERRO =========================")
                    print(f"Ocorreu uma falha ao processar {numero_completo_original}: {e}")
                    print("========================================================")
            
            print("\n🏁 Fim da coleta de dados detalhados.")

            if dados_detalhados:
                try:
                    with open("dados_detalhados.json", "w", encoding="utf-8") as f:
                        json.dump(dados_detalhados, f, ensure_ascii=False, indent=4)
                    print("\n[💾] Dados detalhados salvos com sucesso em 'dados_detalhados.json'.")
                except Exception as e:
                    print(f"\n[❌] Erro ao salvar o arquivo JSON de detalhes: {e}")

    except Exception as e:
        print("\n========================= ERRO CRÍTICO =========================")
        print(f"Ocorreu uma falha na automação: {e}")
        print("========================================================")
    finally:
        if browser_process:
            input("\n... Pressione Enter para fechar o navegador e encerrar o script ...")
            subprocess.run(f"TASKKILL /F /PID {browser_process.pid} /T", shell=True, capture_output=True)
            print("🏁 Navegador fechado. Fim da execução.")

if __name__ == "__main__":
    main()