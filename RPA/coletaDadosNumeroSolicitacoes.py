import time
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, Frame
import json
import random
import sys
import os
import re


project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from bd import database
from portal_bb import fazer_login
from observability import install_print_logger

install_print_logger("robo-coleta-numeros")



# --- CONFIGURAÇÕES OBRIGATÓRIAS ---
BAT_FILE_PATH = Path(__file__).resolve().parent / "abrir_chrome.bat"
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
    print("\n🔢 Verificando paginação...")

    try:
        seletor_50 = 'a.dr-dscr-button:has-text("50")'
        seletor_info = "div.dataTableNumeroRegistros"
        seletor_linhas = 'tbody#pesquisarPendenciaTarefaForm\\:dataTable\\:tb tr'

        # 1. Verifica se o botão '50' está visível. Se não estiver (ex: só tem 5 registros), segue o fluxo.
        botao_50 = frame.locator(seletor_50).first
        if not botao_50.is_visible(timeout=3000):
            print("⚠️ Botão '50' não encontrado ou não necessário (poucos registros). Mantendo paginação atual.")
            return True

        # Captura o texto atual antes de clicar para garantir que mudou depois (opcional, mas robusto)
        try:
            texto_inicial = frame.locator(seletor_info).first.inner_text(timeout=2000).strip()
        except Exception:
            texto_inicial = ""

        try:
            qtd_linhas_inicial = frame.locator(seletor_linhas).count()
        except Exception:
            qtd_linhas_inicial = 0

        print("🖱️  Clicando no botão '50' para expandir registros...")
        botao_50.click(timeout=10000)
        
        print("[⏳] Aguardando atualização da tabela...")

        for _ in range(30): # Tenta por até 15 segundos (30 * 0.5s)
            texto_atual = ""
            try:
                texto_atual = frame.locator(seletor_info).first.inner_text(timeout=1000).strip()
            except Exception:
                pass

            if texto_atual and texto_atual != texto_inicial and texto_atual.startswith("1-"):
                print(f"✅ Paginação atualizada com sucesso. Exibindo: {texto_atual}")
                return True

            try:
                qtd_linhas_atual = frame.locator(seletor_linhas).count()
                if qtd_linhas_atual > qtd_linhas_inicial or qtd_linhas_atual >= 50:
                    print(f"✅ Paginação atualizada com sucesso. Linhas visíveis: {qtd_linhas_atual}")
                    return True
            except Exception:
                pass

            time.sleep(0.5)
        
        try:
            qtd_linhas_atual = frame.locator(seletor_linhas).count()
        except Exception:
            qtd_linhas_atual = 0

        if qtd_linhas_atual > 0:
            print(f"⚠️ Aviso: não foi possível confirmar a paginação pelo contador, mas há {qtd_linhas_atual} linhas. Prosseguindo.")
            return True

        print("❌ Não foi possível confirmar a atualização da paginação nem localizar linhas na tabela.")
        return False

    except Exception as e:
        print(f"[❌] Falha não bloqueante ao alterar paginação: {e}")
        # Retornamos True ou False dependendo se você quer que o robô pare. 
        # Geralmente, falha na paginação não deve parar o robô se ele ainda conseguir ler a página 1.
        return False

def encontrar_botao_proxima_pagina(frame):
    """
    Localiza o botão de próxima página (seta para a direita).
    """
    try:
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
        
        linhas = frame.locator('tbody#pesquisarPendenciaTarefaForm\\:dataTable\\:tb tr').all()
        
        if not linhas:
            print("[⚠️] Nenhuma linha encontrada. Fim da extração.")
            break
            
        for linha in linhas:
            try:
                celula_numero = linha.locator('td').first
                link_numero = celula_numero.locator('a').first
                numero = link_numero.inner_text().strip()
                
                if numero:
                    todos_numeros.add(numero)
                    
            except Exception as e:
                print(f"[❌] Erro ao extrair dados da linha: {e}")
                continue
        
        botao_proximo = encontrar_botao_proxima_pagina(frame)
        if botao_proximo and botao_proximo.is_visible() and botao_proximo.is_enabled():
            print(f"[➡️] Passando para a próxima página...")
            try:
                primeiro_registro_ref = frame.locator('tbody#pesquisarPendenciaTarefaForm\\:dataTable\\:tb tr').first.inner_text()
                
                botao_proximo.click()

                for _ in range(60): 
                    time.sleep(0.5)
                    try:
                        novo_primeiro_registro = frame.locator('tbody#pesquisarPendenciaTarefaForm\\:dataTable\\:tb tr').first.inner_text()
                        if novo_primeiro_registro != primeiro_registro_ref:
                            print("✅ Nova página carregada com sucesso!")
                            break
                    except:
                        continue
                else:
                    print("[❌] A página não foi carregada com novos dados. Interrompendo a extração.")
                    break

                pagina_atual += 1
            except Exception as e:
                print(f"[❌] Erro ao avançar para a próxima página: {e}")
                break
        else:
            print("[⏹️] Fim da paginação. Todos os números extraídos.")
            break
            
    print(f"✅ Extração concluída. {len(todos_numeros)} solicitações ativas encontradas no portal.")
    return list(todos_numeros)

def main():
    """
    Função principal que orquestra a coleta de números e a sincronização de status.
    """
    database.inicializar_banco()

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
            portal_page = fazer_login(context)

            tarefa_frame = acessar_assessoria_e_encontrar_frame(portal_page)
            
            if tarefa_frame:
                if clicar_pesquisar(tarefa_frame):
                    
                    if alterar_registros_por_pagina(tarefa_frame):
                        
                        numeros_atuais_portal = set(extrair_todos_numeros_solicitacoes(tarefa_frame))
                        
                        # --- Lógica de Sincronização ---
                        print("\n[🔄] Sincronizando status das solicitações com o banco de dados...")
                        numeros_abertos_db = set(database.obter_solicitacoes_abertas_db())

                        # 1. Encontra as que foram respondidas
                        respondidas = list(numeros_abertos_db - numeros_atuais_portal)
                        if respondidas:
                            database.marcar_como_respondidas(respondidas)
                            print(f"✅ {len(respondidas)} solicitações foram marcadas como 'Respondido'.")

                        # 2. Insere as novas
                        database.inserir_novas_solicitacoes(list(numeros_atuais_portal))
                        print(f"✅ Novas solicitações (se houver) inseridas no banco de dados.")
                        
                        # 3. Garante que TODAS as ativas estejam como 'Aberto'
                        database.marcar_como_abertas(list(numeros_atuais_portal))
                        print(f"✅ Status de {len(numeros_atuais_portal)} solicitações do portal sincronizado para 'Aberto'.")

                    else:
                        print("❌ Não foi possível alterar o número de registros por página.")
                else:
                    print("❌ Não foi possível realizar a pesquisa. O script será encerrado.")
            else:
                print("❌ Não foi possível encontrar o botão de pesquisa. O script será encerrado.")
            
    except Exception as e:
        print(f"\n========================= ERRO =========================")
        print(f"Ocorreu uma falha na automação: {e}")
        print("========================================================")
    finally:
        # --- BLOCO FINALLY CORRIGIDO ---
        # Este bloco agora executa a mesma lógica do nav.fechar()
        print("\n... Iniciando rotina de fechamento do navegador ...")

        # O 'with sync_playwright()' já cuida de fechar a conexão do Playwright.
        # Nós só precisamos matar o processo do Chrome pela porta 9222.
        
        print("     Procurando e finalizando o processo do Chrome na porta 9222...")
        try:
            if sys.platform == "win32":
                cmd_find_pid = "netstat -ano -p TCP | findstr :9222"
                result = subprocess.run(cmd_find_pid, shell=True, capture_output=True, text=True, check=False)
                output = result.stdout.strip()

                if not output:
                    print("     Nenhum processo encontrado na porta 9222.")
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
                # Lógica para Linux/Mac
                subprocess.run("lsof -t -i:9222 | xargs kill -9", shell=True, check=False, capture_output=True)
                print("     Comando de finalização (Linux/Mac) executado.")

        except Exception as e_kill:
            print(f"     Aviso: Falha ao tentar finalizar o processo da porta 9222: {e_kill}")

        print("--- Rotina de fechamento concluída. Fim da execução. ---")


if __name__ == "__main__":
    main()
