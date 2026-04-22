import time
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright
import json
import re
import sys
import os

# Adiciona o diretório raiz do projeto (onerequest) ao path do Python
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Importa o módulo da pasta 'bd'
from bd import database
from portal_bb import fazer_login

# --- CONFIGURAÇÕES OBRIGATÓRIAS ---
BAT_FILE_PATH = Path(__file__).resolve().parent / "abrir_chrome.bat"
CDP_ENDPOINT = "http://localhost:9222"

def main():
    """
    Função principal que orquestra a automação para buscar detalhes de solicitações
    pendentes no banco de dados e salvar os resultados de volta.
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
            
            print("\n📂 Carregando números de solicitação pendentes do banco de dados...")
            numeros_solicitacoes = database.obter_solicitacoes_pendentes()
            
            if not numeros_solicitacoes:
                print("✅ Nenhuma solicitação pendente encontrada. Trabalho concluído!")
                return
                
            print(f"✅ {len(numeros_solicitacoes)} solicitações pendentes encontradas.")

            for i, numero_completo_original in enumerate(numeros_solicitacoes): 
                try:
                    match = re.match(r"(\d{4})\/(\d{10})", numero_completo_original)
                    if not match:
                        print(f"⚠️ Formato de número inválido: {numero_completo_original}. Pulando.")
                        continue
                    
                    ano = match.group(1)
                    numero = match.group(2)
                    
                    print(f"\n[🔄] {i+1}/{len(numeros_solicitacoes)} - Processando: {numero_completo_original}")
                    
                    url_detalhada = f"https://juridico.bb.com.br/wfj/paginas/negocio/tarefa/pesquisar/buscaRapida.seam?buscaRapidaProcesso=busca_solicitacoes&anoProcesso=&numeroProcesso=&numeroVariacaoProcesso=&anoProcesso=&numeroProcesso=&numeroVariacaoProcesso=&numeroTombo=&numeroCpf=&numeroCnpj=&nomePessoa=&nomePessoaParte=&nomeFantasia=&nomeFantasiaParte=&anoSolicitacaoBuscaRapida={ano}&numeroSolicitacaoBuscaRapida={numero}&anoOficioBuscaRapida=&numeroOficioBuscaRapida="
                    
                    portal_page.goto(url_detalhada, timeout=60000, wait_until="domcontentloaded")
                    
                    portal_page.wait_for_selector('h2.left:has-text("Solicitação : Detalhamento")', timeout=20000)
                    print("    - Página de detalhes carregada.")
                    
                    print("    - Extraindo dados da página principal...")
                    numero_solicitacao_raw = portal_page.locator('span.info_tarefa_label_numero:has-text("Nº da solicitação:") + span.info_tarefa_numero').inner_text()
                    titulo = portal_page.locator('div.left:has(span:has-text("Título:")) span.info_tarefa_label').inner_text()
                    npj_direcionador = portal_page.locator('label.label_padrao:has-text("NPJ Direcionador:") + span span.content').inner_text()
                    prazo = portal_page.locator('label.label_padrao:has-text("Prazo:") + span span.content').inner_text()

                    dados_solicitacao = {
                        "numero_solicitacao": numero_solicitacao_raw.replace("DMI - ", "").strip(),
                        "titulo": titulo.strip(),
                        "npj_direcionador": npj_direcionador.strip(),
                        "prazo": prazo.strip(),
                    }
                    
                    with context.expect_event("page") as popup_info:
                        portal_page.locator("#detalhar\\:j_id106").click()

                    popup_page = popup_info.value
                    popup_page.wait_for_load_state("domcontentloaded", timeout=30000)
                    
                    texto_dmi = popup_page.locator("div.print").first.inner_text()
                    dados_solicitacao["texto_dmi"] = texto_dmi.strip()
                    popup_page.close()
                    print("    - Texto da DMI extraído do popup.")

                    npj_base = dados_solicitacao["npj_direcionador"].split('-')[0]
                    npj_limpo = npj_base.replace('/', '')
                    api_url = f"https://juridico.bb.com.br/paj/resources/app/v1/processo/consulta/{npj_limpo}"
                    
                    api_page = context.new_page()
                    api_response = api_page.goto(api_url)

                    if api_response.ok:
                        api_data = api_page.evaluate("() => JSON.parse(document.body.innerText)")
                        numero_processo = api_data.get("data", {}).get("textoNumeroExternoProcesso", "Não encontrado")
                        polo_indicador = api_data.get("data", {}).get("indicadorPoloBanco", "")
                        polo_map = {"A": "Ativo", "P": "Passivo"}
                        polo = polo_map.get(polo_indicador, "Não definido")
                        
                        dados_solicitacao["numero_processo"] = numero_processo
                        dados_solicitacao["polo"] = polo
                        print("    - Dados da API extraídos.")
                    else:
                        dados_solicitacao["numero_processo"] = "Erro na API"
                        dados_solicitacao["polo"] = "Erro na API"
                    
                    api_page.close()
                    
                    print(f"    - Salvando dados de '{dados_solicitacao['numero_solicitacao']}' no banco de dados...")
                    database.salvar_solicitacao(dados_solicitacao)
                    print("    - Dados salvos com sucesso!")

                except Exception as e:
                    print(f"\n========================= ERRO =========================")
                    print(f"Ocorreu uma falha ao processar {numero_completo_original}: {e}")
                    print("========================================================")
            
            print("\n🏁 Fim da coleta de dados detalhados.")

    except Exception as e:
        print("\n========================= ERRO CRÍTICO =========================")
        print(f"Ocorreu uma falha na automação: {e}")
        print("========================================================")
    finally:
        # --- BLOCO FINALLY CORRIGIDO ---
        # Removi o 'input()' para permitir que o robô rode automaticamente
        
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
                    # Tenta extrair o PID (é o último número na linha)
                    pid_match = re.search(r'(\d+)$', output.splitlines()[0])
                    
                    if pid_match:
                        pid = pid_match.group(1)
                        print(f"     Encontrado processo (PID: {pid}) na porta 9222. Finalizando...")
                        # Comando para matar o PID encontrado
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
