import re
from pathlib import Path
import os
import time
from playwright.sync_api import Page, Frame, TimeoutError

LOGIN_URL = (
    "https://loginweb.bb.com.br/sso/XUI/?realm=/paj"
    "&goto=https://juridico.bb.com.br/wfj#login"
)
PORTAL_HOME_URL = "https://juridico.bb.com.br/paj/juridico/v2"
CONFIRMACAO_PORTAL = 'p:text("Portal Jurídico")'
LOGIN_URL_HINTS = ("loginweb.bb.com.br", "sso/xui")
ACCESS_ERROR_REQUIRED_HINTS = ("erro no acesso", "id e o seu ip")
ACCESS_ERROR_SECURITY_HINTS = ("identificador de seguranca", "identificador de segurança")
SESSION_COOKIE_NAMES = ("JSESSIONID",)
JURIDICO_COOKIE_DOMAINS = ("juridico.bb.com.br", ".juridico.bb.com.br")
JURIDICO_COOKIE_PATHS = ("/", "/wfj", "/paj", "/paj/", "/wfj/")

USER_ENV_KEYS = ("BB_USUARIO", "BB_USERNAME", "PORTAL_BB_USUARIO", "PORTAL_BB_USERNAME")
PASSWORD_ENV_KEYS = ("BB_SENHA", "BB_PASSWORD", "PORTAL_BB_SENHA", "PORTAL_BB_PASSWORD")


def carregar_env_local():
    """Carrega .env local sem depender de python-dotenv."""
    project_root = Path(__file__).resolve().parent.parent
    for env_path in (project_root / ".env", Path(__file__).resolve().parent / ".env"):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def obter_credenciais():
    carregar_env_local()
    usuario = next((os.getenv(key) for key in USER_ENV_KEYS if os.getenv(key)), None)
    senha = next((os.getenv(key) for key in PASSWORD_ENV_KEYS if os.getenv(key)), None)
    if not usuario or not senha:
        raise RuntimeError(
            "Credenciais do portal não encontradas. Configure BB_USUARIO e BB_SENHA no ambiente."
        )
    return usuario, senha


def portal_esta_logado(page: Page) -> bool:
    try:
        if "juridico.bb.com.br" not in page.url.lower():
            return False
        if pagina_erro_acesso(page):
            return False
        return portal_principal_visivel(page)
    except Exception:
        return False


def portal_principal_visivel(page: Page) -> bool:
    try:
        if page.locator(CONFIRMACAO_PORTAL).first.is_visible(timeout=1000):
            return True
    except Exception:
        pass
    return "Portal Jurídico" in texto_pagina(page)


def campos_login_presentes(page: Page) -> bool:
    for seletor in ("#idToken1", "#idToken3"):
        try:
            if page.locator(seletor).count() > 0:
                return True
        except Exception:
            return False
    return False


def texto_pagina(page: Page) -> str:
    try:
        return page.locator("body").inner_text(timeout=3000).strip()
    except Exception:
        return ""


def pagina_erro_acesso(page: Page) -> bool:
    texto = texto_pagina(page).lower()
    if not texto:
        return False
    return all(trecho in texto for trecho in ACCESS_ERROR_REQUIRED_HINTS) and any(
        trecho in texto for trecho in ACCESS_ERROR_SECURITY_HINTS
    )


def extrair_erro_login(page: Page):
    for seletor in ("[role='alert']", ".alert", ".error", ".errors"):
        try:
            mensagens = page.locator(seletor).all()
        except Exception:
            continue
        for mensagem in mensagens:
            try:
                texto = mensagem.inner_text(timeout=1000).strip()
            except Exception:
                continue
            if texto:
                return texto
    return None


def aguardar_documento(page: Page, timeout=30000):
    page.wait_for_load_state("domcontentloaded", timeout=timeout)
    try:
        page.wait_for_function("document.readyState === 'complete'", timeout=timeout)
    except Exception:
        pass


def aguardar_etapa_login(page: Page, timeout=60000):
    deadline = time.monotonic() + (timeout / 1000)
    while time.monotonic() < deadline:
        if pagina_erro_acesso(page):
            raise RuntimeError("Portal retornou página de erro durante o SSO.")
        if portal_esta_logado(page):
            return "authenticated"
        try:
            if page.locator("#idToken1").first.is_visible(timeout=1000):
                return "username"
        except Exception:
            pass
        try:
            if page.locator("#idToken3").first.is_visible(timeout=1000):
                return "password"
        except Exception:
            pass
        erro = extrair_erro_login(page)
        if erro:
            raise RuntimeError(erro)
    raise TimeoutError(
        "Tela de login não carregou dentro do tempo esperado. "
        f"URL atual: {page.url}. Prévia da página: {texto_pagina(page)[:300]}"
    )


def aguardar_campo_senha(page: Page, timeout=60000):
    deadline = time.monotonic() + (timeout / 1000)
    while time.monotonic() < deadline:
        if portal_esta_logado(page):
            raise RuntimeError("Fluxo autenticado sem apresentar a etapa de senha.")
        erro = extrair_erro_login(page)
        if erro:
            raise RuntimeError(erro)
        try:
            campo = page.locator("#idToken3").first
            campo.wait_for(state="visible", timeout=3000)
            return campo
        except Exception:
            pass
    raise TimeoutError("Campo de senha não ficou disponível após informar o usuário.")


def clicar_com_retentativas(page: Page, seletor: str, descricao: str, *, tentativas=3, espera_ms=3000):
    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            botao = page.locator(seletor).first
            botao.wait_for(state="visible", timeout=espera_ms)
            botao.click(timeout=espera_ms, force=True)
            return
        except Exception as exc:
            ultimo_erro = exc
            try:
                page.locator(seletor).first.evaluate("el => el.click()")
                return
            except Exception as js_exc:
                ultimo_erro = js_exc
            if tentativa < tentativas:
                time.sleep(1)
    raise TimeoutError(f"Não foi possível clicar em {descricao}.") from ultimo_erro


def aguardar_autenticado(page: Page, timeout=60000):
    deadline = time.monotonic() + (timeout / 1000)
    while time.monotonic() < deadline:
        if portal_esta_logado(page):
            return
        erro = extrair_erro_login(page)
        if erro:
            raise RuntimeError(erro)
        time.sleep(0.5)
    raise TimeoutError("Autenticação não foi concluída dentro do tempo esperado.")


def aguardar_portal(page: Page):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if portal_principal_visivel(page):
            return
        if pagina_erro_acesso(page):
            raise RuntimeError("Portal retornou página de erro após autenticação.")
        time.sleep(0.5)
    raise TimeoutError(
        "Portal Jurídico não ficou visível após o login. "
        f"URL atual: {page.url}. Prévia da página: {texto_pagina(page)[:300]}"
    )


def limpar_cookies_sessao_portal(context):
    print("\n▶️  Iniciando limpeza seletiva dos cookies de sessão do portal...")
    removidos = 0

    try:
        cookies = context.cookies()
    except Exception:
        cookies = []

    try:
        cdp = context.new_cdp_session(context.pages[0]) if context.pages else None
    except Exception:
        cdp = None

    for cookie in cookies:
        nome = cookie.get("name", "")
        dominio = cookie.get("domain", "")
        path = cookie.get("path", "/")

        if nome not in SESSION_COOKIE_NAMES:
            continue
        if "juridico.bb.com.br" not in dominio:
            continue

        try:
            context.clear_cookies(name=nome, domain=dominio, path=path)
            removidos += 1
        except TypeError:
            context.clear_cookies(name=nome, domain=dominio)
            removidos += 1
        except Exception:
            pass

        if cdp:
            try:
                cdp.send("Network.deleteCookies", {"name": nome, "domain": dominio, "path": path})
            except Exception:
                pass

    for nome in SESSION_COOKIE_NAMES:
        for dominio in JURIDICO_COOKIE_DOMAINS:
            try:
                context.clear_cookies(name=nome, domain=dominio)
                removidos += 1
            except Exception:
                pass
            if cdp:
                for path in JURIDICO_COOKIE_PATHS:
                    try:
                        cdp.send("Network.deleteCookies", {"name": nome, "domain": dominio, "path": path})
                    except Exception:
                        pass

    print(f"✅ Limpeza de cookies de sessão finalizada ({removidos} remoções solicitadas).")


def abrir_popup_dmi(page: Page):
    botao_detalhar = page.locator("#detalhar\\:j_id106").first
    timeout_botao = int(os.getenv("RPA_DMI_BOTAO_TIMEOUT_MS", "30000"))
    tentativas_popup = int(os.getenv("RPA_DMI_POPUP_TENTATIVAS", "3"))
    botao_detalhar.wait_for(state="visible", timeout=timeout_botao)

    for tentativa in range(1, tentativas_popup + 1):
        try:
            with page.context.expect_event("page", timeout=15000) as popup_info:
                botao_detalhar.evaluate(
                    """el => {
                        const event = new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        });
                        el.dispatchEvent(event);
                    }"""
                )
            popup_page = popup_info.value
            popup_page.wait_for_load_state("domcontentloaded", timeout=30000)
            return popup_page
        except Exception as click_error:
            if tentativa < tentativas_popup:
                print(f"    - Popup da DMI não abriu na tentativa {tentativa}/{tentativas_popup}. Tentando novamente...")
                time.sleep(1)
                continue
            raise click_error


def fazer_login(context) -> Page:
    """
    Realiza login direto no Portal Jurídico usando credenciais do ambiente.
    """
    try:
        usuario, senha = obter_credenciais()
        login_timeout = int(os.getenv("RPA_LOGIN_TIMEOUT", "60")) * 1000
        stage_timeout = int(os.getenv("RPA_LOGIN_STAGE_TIMEOUT", "20")) * 1000

        print("🚀 Iniciando login direto no SSO do Portal Jurídico...")
        portal_page = context.pages[0] if context.pages else context.new_page()
        portal_page.goto(LOGIN_URL, timeout=90000, wait_until="domcontentloaded")
        aguardar_documento(portal_page, timeout=30000)

        etapa = aguardar_etapa_login(portal_page, timeout=login_timeout)
        if etapa == "username":
            print("    - Informando usuário no SSO...")
            username_input = portal_page.locator("#idToken1").first
            username_input.fill(usuario)
            clicar_com_retentativas(
                portal_page,
                "#loginButton_0",
                "botão de avanço do usuário",
                tentativas=int(os.getenv("RPA_LOGIN_STAGE_ATTEMPTS", "3")),
            )

        if etapa != "authenticated":
            print("    - Informando senha no SSO...")
            tentativas = int(os.getenv("RPA_LOGIN_STAGE_ATTEMPTS", "3"))
            ultimo_erro = None
            for tentativa in range(1, tentativas + 1):
                password_input = aguardar_campo_senha(portal_page, timeout=login_timeout)
                password_input.fill(senha)
                clicar_com_retentativas(
                    portal_page,
                    "input#loginButton_0[name='callback_4']",
                    "botão de envio da senha",
                    tentativas=1,
                )
                try:
                    aguardar_autenticado(portal_page, timeout=stage_timeout)
                    break
                except TimeoutError as exc:
                    ultimo_erro = exc
                    if tentativa < tentativas:
                        print(f"    - Portal permaneceu na senha na tentativa {tentativa}/{tentativas}. Repetindo...")
                        continue
                    raise ultimo_erro

        print("    - Aguardando a página inicial do portal carregar e confirmar o login...")
        if "Portal Jurídico" not in texto_pagina(portal_page):
            portal_page.goto(PORTAL_HOME_URL, timeout=90000, wait_until="domcontentloaded")
        aguardar_portal(portal_page)
        print("    - Verificacao de login bem-sucedida! Elemento 'Portal Juridico' encontrado.")

        print("\n✅ PROCESSO DE LOGIN FINALIZADO.")
        
        limpar_cookies_sessao_portal(context)
        return portal_page

    except TimeoutError as e:
        print("\n❌ FALHA no processo de login (Timeout).")
        print("   - O robô não conseguiu encontrar um elemento da tela de login ou do portal a tempo.")
        raise e
    except Exception as e:
        print(f"\n❌ FALHA inesperada durante o login: {e}")
        raise e


def coletar_detalhes(page: Page, numero_solicitacao: str) -> dict:
    """Navega para a página de detalhes e extrai todas as informações."""
    match = re.match(r"(\d{4})\/(\d{10})", numero_solicitacao)
    if not match:
        raise ValueError(f"Formato de número inválido: {numero_solicitacao}")
    
    ano, numero = match.groups()
    url_detalhada = f"https://juridico.bb.com.br/wfj/paginas/negocio/tarefa/pesquisar/buscaRapida.seam?buscaRapidaProcesso=busca_solicitacoes&anoSolicitacaoBuscaRapida={ano}&numeroSolicitacaoBuscaRapida={numero}"

    page.goto(
        url_detalhada,
        timeout=int(os.getenv("RPA_DETALHE_GOTO_TIMEOUT_MS", "90000")),
        wait_until="domcontentloaded",
    )
    page.wait_for_selector(
        'h2.left:has-text("Solicitação : Detalhamento")',
        timeout=int(os.getenv("RPA_DETALHE_SELECTOR_TIMEOUT_MS", "30000")),
    )
    
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
    popup_page = abrir_popup_dmi(page)
    texto_dmi = popup_page.locator("div.print").first.inner_text()
    dados_solicitacao["texto_dmi"] = texto_dmi.strip()
    popup_page.close()

    # Lógica de API atualizada
    if dados_solicitacao["npj_direcionador"]:
        npj_base = dados_solicitacao["npj_direcionador"].split('-')[0]
        npj_limpo = npj_base.replace('/', '')
        api_url = f"https://juridico.bb.com.br/paj/resources/app/v1/processo/consulta/{npj_limpo}"

        api_page = page.context.new_page()
        try:
            api_response = api_page.goto(api_url, timeout=30000, wait_until="domcontentloaded")

            if api_response and api_response.ok:
                api_data = api_page.evaluate("() => JSON.parse(document.body.innerText)")

                dados_solicitacao["numero_processo"] = api_data.get("data", {}).get("textoNumeroInventario", "Dado ausente na API")

                polo_indicador = api_data.get("data", {}).get("indicadorPoloBanco", "")
                polo_map = {"A": "Ativo", "P": "Passivo", "N": "Neutro"}
                dados_solicitacao["polo"] = polo_map.get(polo_indicador, "Não definido")

            else:
                status = api_response.status if api_response else "sem resposta"
                dados_solicitacao["numero_processo"] = f"Processo não encontrado (API {status})"
                dados_solicitacao["polo"] = "N/A"
        except Exception as exc:
            dados_solicitacao["numero_processo"] = f"Erro na API: {exc}"
            dados_solicitacao["polo"] = "Erro na API"
        finally:
            api_page.close()
    else:
        dados_solicitacao["numero_processo"] = "NPJ não informado"
        dados_solicitacao["polo"] = "N/A"
    
    return dados_solicitacao
