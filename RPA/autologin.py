import time
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, Frame

# --- CONFIGURAÇÕES OBRIGATÓRIAS ---

# 1. URL da sua extensão.
EXTENSION_URL = "chrome-extension://lnidijeaekolpfeckelhkomndglcglhh/index.html"

# 2. Nome exato do seu arquivo .bat.
BAT_FILE_PATH = Path(__file__).resolve().parent / "abrir_chrome.bat"

# 3. Porta de depuração.
CDP_ENDPOINT = "http://localhost:9222"

def acessar_assessoria_e_encontrar_frame(page: Page) -> Frame:
    """
    Navega para a seção de assessoria e encontra o frame que contém o botão de pesquisa.
    """
    print("[🔁] Acessando seção 'Assessoria - Visão Advogado'...")
    # Aumenta o timeout para dar tempo da página carregar
    page.goto(
        "https://juridico.bb.com.br/wfj/paginas/negocio/tarefa/listarPendenciaTarefa/listar",
        timeout=90000,
        wait_until="domcontentloaded"
    )
    
    print("    - Procurando pelo frame que contém o botão de pesquisa...")
    for frame in page.frames:
        try:
            # O .content() pode falhar em frames de diferentes origens
            if "btPesquisar" in frame.content():
                print(f"[✅] Frame encontrado: {frame.name or '[sem nome]'}")
                return frame
        except Exception:
            # Ignora frames inacessíveis e continua a busca
            continue
    print("[❌] Frame com botão 'Pesquisar' não localizado.")
    return None

def clicar_pesquisar(frame):
    """
    Localiza e clica no botão 'Pesquisar' dentro do frame de forma robusta.
    """
    print("[🔍] Clicando no botão 'Pesquisar'...")
    try:
        # Usa o seletor CSS que você sabe que funciona
        seletor_botao = "input[type='image'][name='pesquisarPendenciaTarefaForm:btPTarefa']"
        
        # Espera o botão de pesquisa ficar visível no frame
        print("    - Aguardando o botão de pesquisa...")
        frame.wait_for_selector(seletor_botao, timeout=20000)
        
        # Clica no botão
        frame.click(seletor_botao)

        print("[⏳] Aguardando carregamento dos registros...")
        # Espera a div com o número de registros aparecer como confirmação de carregamento
        frame.wait_for_selector("div.dataTableNumeroRegistros", timeout=20000)
        
        print("[✅] Registros carregados com sucesso.")
        return True
    except Exception as e:
        print(f"[❌] Falha ao clicar no botão 'Pesquisar': {e}")
        return False


def alterar_registros_por_pagina(frame):
    """
    Função para clicar no botão '50' e aguardar o carregamento da página com os 50 itens.
    """
    print("\n🔢 Clicando no botão '50' para exibir mais registros...")
    
    try:
        seletor_50 = 'a.dr-dscr-button:has-text("50")'
        
        # Clica no botão para alterar a quantidade de registros por página
        frame.click(seletor_50, timeout=10000)
        print("✅ Botão '50' clicado com sucesso!")

        print("[⏳] Aguardando a página recarregar com 50 registros...")
        
        # --- LÓGICA CORRIGIDA ---
        # Espera o elemento de status de registros aparecer E CONTER o texto '1-50'
        seletor_status_registros = 'div.dataTableNumeroRegistros:has-text("1-50")'
        frame.wait_for_selector(seletor_status_registros, timeout=30000)
        # ------------------------
        
        print("✅ Registros por página alterados para 50.")
        return True
    except Exception as e:
        print(f"[❌] Falha ao clicar no botão '50' ou a página não recarregou com os 50 itens: {e}")
        return False

def extrair_solicitacoes(frame):
    """
    Captura os números de solicitação da tabela de pendências.
    """
    print("\n📋 Extraindo números das solicitações da tabela...")
    solicitacoes = []
    
    # Seletor para todas as linhas da tabela
    linhas = frame.locator('tbody#pesquisarPendenciaTarefaForm\\:dataTable\\:tb tr').all()
    
    if not linhas:
        print("[⚠️] Nenhuma linha encontrada na tabela. Verifique se os registros foram carregados.")
        return []
    
    for i, linha in enumerate(linhas):
        try:
            # O número da solicitação está na primeira célula da linha, dentro de um <a>
            celula_numero = linha.locator('td').first
            link_numero = celula_numero.locator('a').first
            numero = link_numero.inner_text().strip()
            
            if numero:
                solicitacoes.append(numero)
            
        except Exception as e:
            print(f"[❌] Erro ao extrair dados da linha {i}: {e}")
            continue
            
    print(f"✅ Extração concluída. {len(solicitacoes)} solicitações encontradas.")
    return solicitacoes

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
            
            # ETAPA 3: Abrir a Extensão e Realizar o Login
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
            
            # ETAPA 4: Navegar para o Portal Jurídico na mesma guia que foi aberta
            print("    - Navegando para o Portal Jurídico para garantir o carregamento completo...")
            portal_page.goto("https://juridico.bb.com.br/paj/juridico#redirect-completed")
            portal_page.wait_for_selector('p:text("Portal Jurídico")')
            
            print("\n✅ PROCESSO DE LOGIN FINALIZADO. O robô pode continuar.")
            
            # ETAPA 5: Limpeza seletiva de cookies
            print("▶️  Iniciando a limpeza seletiva de cookies...")
            all_cookies = context.cookies()
            print(f"    Cookies antes da limpeza: {len(all_cookies)} cookies encontrados.")

            print("    - Tentando remover o cookie 'JSESSIONID'...")
            context.clear_cookies(name="JSESSIONID", domain=".juridico.bb.com.br")
            context.clear_cookies(name="JSESSIONID", domain="juridico.bb.com.br")
            
            remaining_cookies = context.cookies()
            print(f"    Cookies após a limpeza: {len(remaining_cookies)} cookies restantes.")
            
            print("✅ Limpeza de cookies 'JSESSIONID' finalizada.")
            
            # ETAPA 6: Navegar para o módulo de assessoria e clicar no botão
            # ESTE BLOCO DE CÓDIGO FOI MOVIDO PARA DENTRO DO 'with sync_playwright() as p:'
            tarefa_frame = acessar_assessoria_e_encontrar_frame(portal_page)
            
            if tarefa_frame:
                if clicar_pesquisar(tarefa_frame):
                    if alterar_registros_por_pagina(tarefa_frame):
                        # --- NOVA ETAPA: EXTRAIR AS SOLICITAÇÕES ---
                        numeros_solicitacoes = extrair_solicitacoes(tarefa_frame)
                        print("Números capturados:", numeros_solicitacoes)
                        # Agora você pode processar essa lista (salvar em JSON, etc.)
                    else:
                        print("❌ Não foi possível alterar o número de registros por página.")
                else:
                    print("❌ Não foi possível realizar a pesquisa. O script será encerrado.")
                    
            else:
                print("❌ Não foi possível encontrar o botão de pesquisa. O script será encerrado.")
                raise Exception("Botão 'Pesquisar' não encontrado dentro de um frame.")
            
    except Exception as e:
        print("\n========================= ERRO =========================")
        print(f"Ocorreu uma falha na automação: {e}")
        print("========================================================")
    finally:
        # ETAPA FINAL: Finalização Limpa
        if browser_process:
            input("\n... Pressione Enter para fechar o navegador e encerrar o script ...")
            subprocess.run(f"TASKKILL /F /PID {browser_process.pid} /T", shell=True, capture_output=True)
            print("🏁 Navegador fechado. Fim da execução.")

if __name__ == "__main__":
    main()