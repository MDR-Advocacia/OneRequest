import time
import sys
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from bd import database

def entrar_no_frame_principal(driver):
    driver.switch_to.default_content()
    # Tenta achar direto
    if len(driver.find_elements(By.NAME, "pesquisarPendenciaTarefaForm:btPTarefa")) > 0:
        return True
    # Busca frames
    frames = driver.find_elements(By.TAG_NAME, "iframe") + driver.find_elements(By.TAG_NAME, "frame")
    for frame in frames:
        try:
            driver.switch_to.frame(frame)
            if len(driver.find_elements(By.NAME, "pesquisarPendenciaTarefaForm:btPTarefa")) > 0:
                return True 
            driver.switch_to.default_content()
        except: driver.switch_to.default_content()
    return False

def extrair_numeros_da_pagina(driver):
    numeros = []
    try:
        linhas = driver.find_elements(By.XPATH, "//tbody[contains(@id, 'dataTable:tb')]//tr")
        for linha in linhas:
            try:
                texto = linha.text
                if "/" in texto:
                    import re
                    match = re.search(r'\d{4}/\d+', texto)
                    if match: numeros.append(match.group(0))
            except: continue
    except: pass
    return numeros

def obter_contador_registros(driver):
    try: return driver.find_element(By.CSS_SELECTOR, "div.dataTableNumeroRegistros").text.strip()
    except: return ""

def sincronizar_solicitacoes(driver):
    wait = WebDriverWait(driver, 30)

    print("🏠 Home acessada (pré-aquecimento)...")
    # Home já foi acessada no login, apenas reforça
    
    print("🔁 Acessando Lista de Tarefas...")
    url_lista = "https://juridico.bb.com.br/wfj/paginas/negocio/tarefa/listarPendenciaTarefa/listar"
    
    # --- PROTEÇÃO CONTRA TIMEOUT ---
    try:
        driver.get(url_lista)
    except TimeoutException:
        print("⚠️ Aviso: Carregamento lento detectado. Forçando parada para verificar conteúdo...")
        try: driver.execute_script("window.stop();")
        except: pass
    except Exception as e:
        print(f"❌ Erro de navegação: {e}")

    # Verifica Sessão
    if "Sessão expirada" in driver.page_source:
        print("⚠️ Sessão expirada. Tentando refresh...")
        driver.refresh()
        time.sleep(3)

    print("⏳ Localizando tabela...")
    if not entrar_no_frame_principal(driver):
        print("❌ Tabela não encontrada. Tentando recarregar...")
        driver.refresh()
        time.sleep(5)
        if not entrar_no_frame_principal(driver):
            print("❌ Falha crítica: Tabela inacessível.")
            return

    print("🔍 Pesquisando...")
    try:
        btn = wait.until(EC.element_to_be_clickable((By.NAME, "pesquisarPendenciaTarefaForm:btPTarefa")))
        driver.execute_script("arguments[0].click();", btn)
        
        wait.until(EC.presence_of_element_located((By.ID, "pesquisarPendenciaTarefaForm:dataTable:tb")))
        
        # Tenta mudar para 50 registros
        try:
            botoes_50 = driver.find_elements(By.XPATH, "//a[contains(text(), '50')]")
            if botoes_50:
                driver.execute_script("arguments[0].click();", botoes_50[0])
                time.sleep(2)
        except: pass

    except Exception as e:
        print(f"❌ Erro na interação inicial: {e}")
        return

    # --- LOOP DE COLETA ---
    todos_numeros_portal = set()
    pagina = 1
    
    print("\n📋 Coletando dados...")
    while True:
        entrar_no_frame_principal(driver)
        
        try:
            wait.until(EC.visibility_of_element_located((By.XPATH, "//tbody[contains(@id, 'dataTable:tb')]")))
        except:
            print("⏹️ Tabela vazia ou fim.")
            break

        numeros_pag = extrair_numeros_da_pagina(driver)
        if numeros_pag:
            print(f"📄 Pág {pagina}: {len(numeros_pag)} itens.")
            todos_numeros_portal.update(numeros_pag)
        else:
            print(f"⏹️ Pág {pagina} sem dados.")
            break
        
        try:
            botao_proximo = driver.find_element(By.CSS_SELECTOR, "a.mi--chevron-right")
            if "disabled" in botao_proximo.get_attribute("class") or not botao_proximo.get_attribute("onclick"):
                break
            
            contador_atual = obter_contador_registros(driver)
            driver.execute_script("arguments[0].click();", botao_proximo)
            
            try: WebDriverWait(driver, 10).until(lambda d: obter_contador_registros(d) != contador_atual)
            except: pass
            pagina += 1
        except: break

    if todos_numeros_portal:
        print(f"\n🔄 Sincronizando {len(todos_numeros_portal)} registros...")
        numeros_abertos_db = set(database.obter_solicitacoes_abertas_db())
        respondidas = list(numeros_abertos_db - todos_numeros_portal)
        
        if respondidas:
            database.marcar_como_respondidas(respondidas)
            print(f"✅ {len(respondidas)} finalizadas.")
            
        database.inserir_novas_solicitacoes(list(todos_numeros_portal))
        database.marcar_como_abertas(list(todos_numeros_portal))
        print("✅ Sucesso!")
    else:
        print("⚠️ Nada coletado.")