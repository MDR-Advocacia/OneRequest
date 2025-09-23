import re
from playwright.sync_api import Page, Frame

EXTENSION_URL = "chrome-extension://lnidijeaekolpfeckelhkomndglcglhh/index.html"

def fazer_login(context) -> Page:
    """Realiza o processo de login através da extensão e retorna a página principal do portal."""
    print(f"🚀 Navegando diretamente para a URL da extensão...")
    extension_page = context.pages[0] if context.pages else context.new_page()
    extension_page.goto(EXTENSION_URL)
    extension_page.wait_for_load_state("domcontentloaded")

    print("    - Localizando o campo de busca na extensão...")
    search_input = extension_page.get_by_placeholder("Digite ou selecione um sistema pra acessar")
    search_input.wait_for(state="visible", timeout=5000)
    search_input.fill("banco do")

    with context.expect_event('page') as new_page_info:
        print("🖱️  Clicando no item de menu 'Banco do Brasil - Intranet'...")
        login_button = extension_page.locator('div[role="menuitem"]:not([disabled])', has_text="Banco do Brasil - Intranet").first
        login_button.click(timeout=10000)
        print("    - Clicando no botão de confirmação 'ACESSAR'...")
        extension_page.get_by_role("button", name="ACESSAR").click(timeout=5000)
    
    portal_page = new_page_info.value
    extension_page.close()
    
    print("✔️  Login confirmado! Aguardando a autenticação se propagar.")
    portal_page.wait_for_timeout(5000)
    portal_page.goto("https://juridico.bb.com.br/paj/juridico#redirect-completed")
    portal_page.wait_for_selector('p:text("Portal Jurídico")')
    print("\n✅ PROCESSO DE LOGIN FINALIZADO.")
    
    print("\n▶️  Iniciando a limpeza seletiva de cookies...")
    context.clear_cookies(name="JSESSIONID", domain=".juridico.bb.com.br")
    context.clear_cookies(name="JSESSIONID", domain="juridico.bb.com.br")
    print("✅ Limpeza de cookies 'JSESSIONID' finalizada.")
    return portal_page

def coletar_detalhes(page: Page, numero_solicitacao: str) -> dict:
    """Navega para a página de detalhes e extrai todas as informações."""
    match = re.match(r"(\d{4})\/(\d{10})", numero_solicitacao)
    if not match:
        raise ValueError(f"Formato de número inválido: {numero_solicitacao}")
    
    ano, numero = match.groups()
    url_detalhada = f"https://juridico.bb.com.br/wfj/paginas/negocio/tarefa/pesquisar/buscaRapida.seam?buscaRapidaProcesso=busca_solicitacoes&anoSolicitacaoBuscaRapida={ano}&numeroSolicitacaoBuscaRapida={numero}"
    
    page.goto(url_detalhada, timeout=60000, wait_until="domcontentloaded")
    page.wait_for_selector('h2.left:has-text("Solicitação : Detalhamento")', timeout=20000)
    
    # Extração da página principal
    numero_solicitacao_raw = page.locator('span.info_tarefa_label_numero:has-text("Nº da solicitação:") + span.info_tarefa_numero').inner_text()
    titulo = page.locator('div.left:has(span:has-text("Título:")) span.info_tarefa_label').inner_text()
    prazo = page.locator('label.label_padrao:has-text("Prazo:") + span span.content').inner_text()
    
    try:
        npj_direcionador = page.locator('label.label_padrao:has-text("NPJ Direcionador:") + span span.content').inner_text()
    except Exception:
        npj_direcionador = ""

    dados_solicitacao = {
        "numero_solicitacao": numero_solicitacao_raw.replace("DMI - ", "").strip(),
        "titulo": titulo.strip(),
        "npj_direcionador": npj_direcionador.strip(),
        "prazo": prazo.strip(),
    }

    # Extração do Popup
    with page.context.expect_event("page") as popup_info:
        page.locator("#detalhar\\:j_id106").click()
    popup_page = popup_info.value
    popup_page.wait_for_load_state("domcontentloaded")
    texto_dmi = popup_page.locator("div.print").first.inner_text()
    dados_solicitacao["texto_dmi"] = texto_dmi.strip()
    popup_page.close()

    # Lógica de API atualizada
    if dados_solicitacao["npj_direcionador"]:
        npj_base = dados_solicitacao["npj_direcionador"].split('-')[0]
        npj_limpo = npj_base.replace('/', '')
        api_url = f"https://juridico.bb.com.br/paj/resources/app/v1/processo/consulta/{npj_limpo}"
        
        api_page = page.context.new_page()
        api_response = api_page.goto(api_url)
        
        if api_response.ok:
            api_data = api_page.evaluate("() => JSON.parse(document.body.innerText)")
            
            dados_solicitacao["numero_processo"] = api_data.get("data", {}).get("textoNumeroInventario", "Dado ausente na API")
            
            polo_indicador = api_data.get("data", {}).get("indicadorPoloBanco", "")
            
            # ###############################################################
            # ## AQUI ESTÁ A CORREÇÃO!                                     ##
            # ## Adicionamos o "N" para "Neutro" ao dicionário de mapeamento ##
            # ###############################################################
            polo_map = {"A": "Ativo", "P": "Passivo", "N": "Neutro"}
            dados_solicitacao["polo"] = polo_map.get(polo_indicador, "Não definido")
            # ###############################################################
            
        else:
            dados_solicitacao["numero_processo"] = f"Processo não encontrado (API {api_response.status})"
            dados_solicitacao["polo"] = "N/A"
        api_page.close()
    else:
        dados_solicitacao["numero_processo"] = "NPJ não informado"
        dados_solicitacao["polo"] = "N/A"
    
    return dados_solicitacao