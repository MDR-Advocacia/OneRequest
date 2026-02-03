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

# --- CONFIGURAÇÕES ---
# BAT_FILE_PATH não é mais usado para abrir, pois faremos isso manualmente
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

        # 1. Verifica se o botão '50' está visível. Se não estiver (ex: só tem 5 registros), segue o fluxo.
        if not frame.locator(seletor_50).is_visible():
            print("⚠️ Botão '50' não encontrado ou não necessário (poucos registros). Mantendo paginação atual.")
            return True

        # Captura o texto atual antes de clicar para garantir que mudou depois
        seletor_info = "div.dataTableNumeroRegistros"
        try:
            texto_inicial = frame.locator(seletor_info).first.inner_text()
        except:
            texto_inicial = ""

        print("🖱️  Clicando no botão '50' para expandir registros...")
        frame.click(seletor_50, timeout=10000)
        
        print("[⏳] Aguardando atualização da tabela...")

        # 2. Espera genérica
        frame.wait_for_selector(seletor_info, state="visible", timeout=30000)

        # 3. Validação extra
        for _ in range(20): 
            texto_atual = frame.locator(seletor_info).first.inner_text().strip()
            if texto_atual != texto_inicial and texto_atual.startswith("1-"):
                print(f"✅ Paginação atualizada com sucesso. Exibindo: {texto_atual}")
                return True
            time.sleep(0.5)
        
        print(f"⚠️ Aviso: O texto da paginação não mudou ({texto_inicial}), mas o elemento está visível. Prosseguindo.")
        return True

    except Exception as e:
        print(f"[❌] Falha não bloqueante ao alterar paginação: {e}")
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
    Função principal adaptada para Automação Assistida (sem login, sem fechar browser).
    """
    database.inicializar_banco()

    # --- 1. NÃO abre o Chrome via código ---
    print("⚠️ MODO ASSISTIDO: Certifique-se de que o Chrome já está aberto na porta 9222 e logado.")

    try:
        with sync_playwright() as p:
            browser = None
            # --- 2. Conecta ao Chrome existente ---
            for attempt in range(5):
                try:
                    print(f"    Tentativa de conexão nº {attempt + 1}...")
                    browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
                    print("✅ Conectado com sucesso ao navegador!")
                    break 
                except Exception:
                    time.sleep(2)
            
            if not browser:
                raise ConnectionError("Não foi possível conectar. Rode o 'abrir_chrome.bat' antes!")

            context = browser.contexts[0]
            
            # --- 3. Pula Login e Pega a Aba Atual ---
            if not context.pages:
                print("❌ Nenhuma aba encontrada. Abra o Portal Jurídico no Chrome.")
                return

            # Assume que a primeira aba é a que vamos usar
            portal_page = context.pages[0]
            print(f"✅ Usando a página já aberta: {portal_page.title()}")
            
            # --- 4. Continua o fluxo normal de navegação (sem login) ---
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
        # --- 5. NÃO mata o Chrome ---
        print("\n🏁 Script finalizado. O Chrome continua aberto para o próximo robô.")
        # Removido todo o bloco de TASKKILL para não fechar o navegador.

if __name__ == "__main__":
    main()