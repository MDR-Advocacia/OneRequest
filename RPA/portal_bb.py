import time
import json
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

def buscar_texto_flexivel(driver, texto_label):
    xpaths = [
        f"//label[contains(text(), '{texto_label}')]/following-sibling::span",
        f"//*[contains(text(), '{texto_label}')]/following-sibling::*[1]",
        f"//td[contains(text(), '{texto_label}')]/following-sibling::td[1]",
        f"(//*[contains(text(), '{texto_label}')])[1]/following::span[1]"
    ]
    for xpath in xpaths:
        try:
            elemento = driver.find_element(By.XPATH, xpath)
            texto = elemento.text.strip()
            if texto: return texto
        except: continue
    return ""

def encontrar_botao_visivel(driver, seletores):
    """
    Percorre a lista de seletores e retorna o PRIMEIRO elemento que:
    1. Existe no DOM
    2. É VISÍVEL (tamanho > 0)
    """
    for xpath in seletores:
        try:
            elementos = driver.find_elements(By.XPATH, xpath)
            for elem in elementos:
                if elem.is_displayed():
                    print(f"      👀 Botão VISÍVEL encontrado: {xpath}")
                    return elem
        except:
            continue
    return None

def coletar_detalhes(driver, numero_solicitacao):
    print(f"\n🔍 --- INICIANDO COLETA: {numero_solicitacao} ---")
    
    match = re.match(r"(\d{4})\/(\d{10})", numero_solicitacao)
    if not match: return None
    
    ano, numero = match.groups()
    url_detalhada = (
        f"https://juridico.bb.com.br/wfj/paginas/negocio/tarefa/pesquisar/buscaRapida.seam?"
        f"buscaRapidaProcesso=busca_solicitacoes&"
        f"anoSolicitacaoBuscaRapida={ano}&"
        f"numeroSolicitacaoBuscaRapida={numero}"
    )
    
    driver.get(url_detalhada)
    wait = WebDriverWait(driver, 20)
    
    dados = {
        "numero_solicitacao": numero_solicitacao,
        "titulo": "", "prazo": "", "npj_direcionador": "",
        "texto_dmi": "", "numero_processo": "", "polo": "",
        "status": "Aberto", "data_coleta": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        # --- ETAPA 1: DADOS DA TELA ---
        print("   1️⃣ Buscando dados na tela...")
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Título')]")))
            dados["titulo"] = buscar_texto_flexivel(driver, "Título")
            dados["prazo"] = buscar_texto_flexivel(driver, "Prazo")
            dados["npj_direcionador"] = buscar_texto_flexivel(driver, "NPJ Direcionador") or buscar_texto_flexivel(driver, "NPJ")
            print(f"      🔹 Título: {dados['titulo'] or '[NÃO]'}")
        except Exception as e:
            print(f"      ❌ Erro na extração básica: {e}")

        
        # --- ETAPA 2: POPUP (LÓGICA CORRIGIDA) ---
        print("   2️⃣ Abrindo Popup DMI...")
        janela_principal = driver.current_window_handle
        janelas_antes = len(driver.window_handles)
        sucesso_popup = False
        
        # Seletores ajustados para evitar inputs ocultos
        seletores_botao = [
            "//input[@type='image'][contains(@id, 'detalhar')]", # Prioriza input type='image'
            "//img[contains(@title, 'Detalhar')]/..", # Imagem com título
            "//img[contains(@src, 'detalhar')]/..", # Imagem pelo source
            "//a[contains(@onclick, 'detalhar')]", # Link com onclick
            "//*[contains(@id, 'detalhar') and not(@type='hidden')]" # Qualquer coisa com ID detalhar que não seja hidden
        ]

        for tentativa in range(1, 4):
            if sucesso_popup: break
            
            print(f"      🔄 Tentativa {tentativa} de abrir Popup...")
            
            # Busca APENAS elementos visíveis
            btn = encontrar_botao_visivel(driver, seletores_botao)
            
            if not btn:
                print("      ❌ Nenhum botão VISÍVEL encontrado no DOM.")
                break

            try:
                # ESTRATÉGIA DE CLIQUE
                if tentativa == 1:
                    # ActionChains é o melhor para simular mouse real
                    ActionChains(driver).move_to_element(btn).pause(0.5).click().perform()
                    print("      🖱️ Clique via ActionChains...")
                elif tentativa == 2:
                    btn.click()
                    print("      🖱️ Clique Nativo...")
                else:
                    driver.execute_script("arguments[0].click();", btn)
                    print("      💻 Clique via JavaScript...")

                # Espera inteligente pela nova janela
                try:
                    WebDriverWait(driver, 8).until(lambda d: len(d.window_handles) > janelas_antes)
                    
                    # Identifica a nova janela
                    janelas_novas = driver.window_handles
                    # Pega a janela que não estava na lista antes
                    nova_janela = [j for j in janelas_novas if j != janela_principal][-1]
                    
                    driver.switch_to.window(nova_janela)
                    print("      ➡️ Janela nova detectada!")
                    
                    # Extração
                    wait_popup = WebDriverWait(driver, 10)
                    wait_popup.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                    
                    try:
                        try:
                            elem = driver.find_element(By.CSS_SELECTOR, "div.print")
                            dados["texto_dmi"] = elem.text.strip()
                        except:
                            dados["texto_dmi"] = driver.find_element(By.TAG_NAME, "body").text.strip()
                        
                        print(f"      ✅ Texto capturado! ({len(dados['texto_dmi'])} chars)")
                        sucesso_popup = True
                    except:
                        print("      ⚠️ Janela abriu mas falhou ao ler texto.")
                    
                    # Fecha popup
                    driver.close()
                    driver.switch_to.window(janela_principal)
                    
                except:
                    print(f"      ⚠️ Clique feito, mas janela não abriu na tentativa {tentativa}.")
                    time.sleep(2)

            except Exception as e:
                print(f"      ⚠️ Erro ao clicar: {str(e)[:100]}...")
                if driver.current_window_handle != janela_principal:
                    driver.switch_to.window(janela_principal)
                time.sleep(1)

        if not dados["texto_dmi"]:
            print("      ❌ Falha final: Não foi possível obter o texto do DMI.")


        # --- ETAPA 3: API ---
        print("   3️⃣ API Interna...")
        if dados["npj_direcionador"]:
            try:
                # Extrai apenas números do NPJ
                npj_limpo = "".join(filter(str.isdigit, dados["npj_direcionador"].split('-')[0]))
                
                # Abre nova aba
                driver.switch_to.new_window('tab')
                driver.get(f"https://juridico.bb.com.br/paj/resources/app/v1/processo/consulta/{npj_limpo}")
                
                try:
                    conteudo = driver.find_element(By.TAG_NAME, "body").text
                    js = json.loads(conteudo)
                    if "data" in js and js["data"]:
                        api_data = js["data"]
                        dados["numero_processo"] = api_data.get("textoNumeroExternoProcesso") or api_data.get("textoNumeroInventario")
                        polo = api_data.get("indicadorPoloBanco", "")
                        dados["polo"] = "Ativo" if polo == "A" else "Passivo" if polo == "P" else "Neutro"
                        print(f"      ✅ API OK: {dados['numero_processo']} | {dados['polo']}")
                except: pass
                
                driver.close()
                driver.switch_to.window(janela_principal)
            except:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(janela_principal)
        else:
            print("      ⚠️ API pulada.")

        return dados

    except Exception as e:
        print(f"❌ Erro Geral: {e}")
        return None