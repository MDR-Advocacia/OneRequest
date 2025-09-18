import time
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, Frame
import json
import random

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
    page.goto(
        "https://juridico.bb.com.br/wfj/paginas/negocio/tarefa/listarPendenciaTarefa/listar",
        timeout=90000,
        wait_until="domcontentloaded"
    )

    print("    - Procurando pelo frame que contém o botão de pesquisa...")
    for frame in page.frames:
        try:
            if "btPesquisar" in frame.content():
                print(f"[✅] Frame encontrado: {frame.name or '[sem nome]'}")
                return frame
        except Exception:
            continue
    print("[❌] Frame com botão 'Pesquisar' não localizado.")
    return None

def clicar_pesquisar(frame):
    """
    Localiza e clica no botão 'Pesquisar' dentro do frame de forma robusta.
    """
    print("[🔍] Clicando no botão 'Pesquisar'...")
    try:
        seletor_botao = "input[type='image'][name='pesquisarPendenciaTarefaForm:btPTarefa']"

        print("    - Aguardando o botão de pesquisa...")
        frame.wait_for_selector(seletor_botao, timeout=20000)

        frame.click(seletor_botao)

        print("[⏳] Aguardando carregamento dos registros...")
        frame.wait_for_selector("div.dataTableNumeroRegistros", timeout=20000)

        print("[✅] Registros carregados com sucesso.")
        return True
    except Exception as e:
        print(f"[❌] Falha ao clicar no botão 'Pesquisar': {e}")
        return False

def alterar_registros_por_pagina(frame):
    """
    Função para clicar no botão '50' e aguardar o carregamento da página.
    """
    print("\n🔢 Clicando no botão '50' para exibir mais registros...")

    try:
        seletor_50 = 'a.dr-dscr-button:has-text("50")'

        frame.click(seletor_50, timeout=10000)
        print("✅ Botão '50' clicado com sucesso!")

        print("[⏳] Aguardando a página recarregar com 50 registros...")
        seletor_status_registros = 'div.dataTableNumeroRegistros:has-text("1-50")'
        frame.wait_for_selector(seletor_status_registros, timeout=30000)
        print("✅ Registros por página alterados para 50.")

        return True
    except Exception as e:
        print(f"[❌] Falha ao clicar no botão '50' ou a página não recarregou: {e}")
        return False

def encontrar_botao_proxima_pagina(frame):
    """
    Localiza o botão de próxima página (seta para a direita).
    """
    try:
        # Tenta localizar o botão pela classe de ícone
        botao_proximo = frame.locator('a.mi--chevron-right')
        if botao_proximo.is_visible() and botao_proximo.is_enabled():
            return botao_proximo
    except Exception:
        pass
    
    return None

def extrair_todos_numeros_solicitacoes(frame):
    """
    Extrai todos os números de solicitação de todas as páginas da tabela.
    """
    print("\n📋 Extraindo números das solicitações da tabela...")
    todos_numeros = set()
    pagina_atual = 1
    
    while True:
        print(f"[📄] Lendo página {pagina_atual}...")
        
        # O seletor para as linhas é o mesmo do código original
        linhas = frame.locator('tbody#pesquisarPendenciaTarefaForm\\:dataTable\\:tb tr').all()
        
        if not linhas:
            print("[⚠️] Nenhuma linha encontrada. Fim da extração.")
            break
            
        for linha in linhas:
            try:
                # Extrai apenas o número da solicitação da primeira célula de cada linha
                celula_numero = linha.locator('td').first
                link_numero = celula_numero.locator('a').first
                numero = link_numero.inner_text().strip()
                
                if numero:
                    todos_numeros.add(numero)
                    
            except Exception as e:
                print(f"[❌] Erro ao extrair dados da linha: {e}")
                continue
        
        # Tenta avançar para a próxima página
        botao_proximo = encontrar_botao_proxima_pagina(frame)
        if botao_proximo and botao_proximo.is_visible() and botao_proximo.is_enabled():
            print(f"[➡️] Passando para a próxima página...")
            try:
                # Pega o primeiro registro da página atual para usar como referência
                primeiro_registro_ref = frame.locator('tbody#pesquisarPendenciaTarefaForm\\:dataTable\\:tb tr').first.inner_text()
                
                # Clica no botão
                botao_proximo.click()

                # Espera até que o primeiro registro da página seja diferente
                for _ in range(60): # Tenta por até 30 segundos
                    time.sleep(0.5)
                    try:
                        novo_primeiro_registro = frame.locator('tbody#pesquisarPendenciaTarefaForm\\:dataTable\\:tb tr').first.inner_text()
                        if novo_primeiro_registro != primeiro_registro_ref:
                            print("✅ Nova página carregada com sucesso!")
                            break
                    except:
                        continue
                else:
                    # Se o loop terminar sem encontrar um novo registro, significa que a página não mudou
                    print("[❌] A página não foi carregada com novos dados. Interrompendo a extração.")
                    break

                pagina_atual += 1
            except Exception as e:
                print(f"[❌] Erro ao avançar para a próxima página: {e}")
                break
        else:
            print("[⏹️] Fim da paginação. Todos os números extraídos.")
            break
            
    print(f"✅ Extração concluída. {len(todos_numeros)} solicitações únicas encontradas.")
    return list(todos_numeros)

def main():
    """
    Função principal que orquestra toda a automação, do início ao fim.
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
            
            print("▶️  Iniciando a limpeza seletiva de cookies...")
            all_cookies = context.cookies()
            print(f"    Cookies antes da limpeza: {len(all_cookies)} cookies encontrados.")

            print("    - Tentando remover o cookie 'JSESSIONID'...")
            context.clear_cookies(name="JSESSIONID", domain=".juridico.bb.com.br")
            context.clear_cookies(name="JSESSIONID", domain="juridico.bb.com.br")
            
            remaining_cookies = context.cookies()
            print(f"    Cookies após a limpeza: {len(remaining_cookies)} cookies restantes.")
            
            print("✅ Limpeza de cookies 'JSESSIONID' finalizada.")
            
            tarefa_frame = acessar_assessoria_e_encontrar_frame(portal_page)
            
            if tarefa_frame:
                if clicar_pesquisar(tarefa_frame):
                    if alterar_registros_por_pagina(tarefa_frame):
                        numeros_extraidos = extrair_todos_numeros_solicitacoes(tarefa_frame)
                        print(f"✅ Extração de números de solicitação concluída. Total: {len(numeros_extraidos)}.")
                        
                        # Salva a lista de números extraídos em um arquivo JSON
                        if numeros_extraidos:
                            try:
                                with open("numeros_solicitacoes.json", "w", encoding="utf-8") as f:
                                    json.dump(numeros_extraidos, f, ensure_ascii=False, indent=2)
                                print("\n💾 Números salvos com sucesso em 'numeros_solicitacoes.json'.")
                            except Exception as e:
                                print(f"\n❌ Erro ao salvar o arquivo JSON: {e}")

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
        if browser_process:
            input("\n... Pressione Enter para fechar o navegador e encerrar o script ...")
            subprocess.run(f"TASKKILL /F /PID {browser_process.pid} /T", shell=True, capture_output=True)
            print("🏁 Navegador fechado. Fim da execução.")

if __name__ == "__main__":
    main()