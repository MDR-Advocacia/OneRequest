import time
import subprocess
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, Frame
import json
import random
import sys
import os
import re


project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))

from RPA import api_client as database
from portal_bb import fazer_login
from observability import install_print_logger
from lock_chrome import LockChrome

install_print_logger("robo-coleta-numeros")



# --- CONFIGURAÇÕES OBRIGATÓRIAS ---
BAT_FILE_PATH = Path(__file__).resolve().parent / "abrir_chrome.bat"
CDP_ENDPOINT = "http://localhost:9222"
ASSESSORIA_URL = "https://juridico.bb.com.br/wfj/paginas/negocio/tarefa/listarPendenciaTarefa/listar"
INFO_REGISTROS_SELECTOR = "div.dataTableNumeroRegistros"
# Link JSF que gera o relatorio (PDF) com TODAS as solicitacoes de uma vez.
REPORT_LINK_SELECTOR = "a:has-text('Imprimir Relatório')"
# No PDF os numeros quebram em 2 linhas (coluna estreita): 'YYYY/NNNNNN' + 'NNNN'.
# Por isso juntamos os digitos separados por espaco/quebra antes de casar este padrao.
NUMERO_SOLICITACAO_PDF_PATTERN = re.compile(r"\d{4}/\d{10}")


class ErroTecnicoPortal(Exception):
    pass


def pagina_erro_tecnico(page: Page) -> bool:
    try:
        if "errodesconhecido.seam" in page.url.lower():
            return True
        texto = page.locator("body").inner_text(timeout=1000).lower()
        return "aconteceu um problema técnico" in texto or "aconteceu um problema tecnico" in texto
    except Exception:
        return False


def verificar_erro_tecnico(page: Page, contexto: str):
    if pagina_erro_tecnico(page):
        raise ErroTecnicoPortal(f"Portal caiu na página de erro técnico durante {contexto}. URL atual: {page.url}")


def limpar_cookie_erro_wfj(context):
    print("    - Limpando somente JSESSIONID do WFJ/raiz...")
    removidos = 0
    dominios = ("juridico.bb.com.br", ".juridico.bb.com.br")
    paths = ("/wfj", "/wfj/", "/")

    try:
        page = context.pages[0] if context.pages else None
        cdp = context.new_cdp_session(page) if page else None
    except Exception:
        cdp = None

    for dominio in dominios:
        for path in paths:
            try:
                context.clear_cookies(name="JSESSIONID", domain=dominio, path=path)
                removidos += 1
                continue
            except TypeError:
                pass
            except Exception:
                pass

            if cdp:
                try:
                    cdp.send("Network.deleteCookies", {"name": "JSESSIONID", "domain": dominio, "path": path})
                    removidos += 1
                except Exception:
                    pass

    print(f"✅ Limpeza seletiva WFJ finalizada ({removidos} remoções solicitadas).")


def obter_total_registros(frame) -> int | None:
    try:
        texto = frame.locator(INFO_REGISTROS_SELECTOR).first.inner_text(timeout=3000)
    except Exception:
        return None

    match = re.search(r"total\s*de\s*(\d+)", texto.lower())
    if not match:
        print(f"⚠️ Não foi possível identificar o total no contador: {texto!r}")
        return None

    total = int(match.group(1))
    print(f"📊 Total informado pelo portal: {total} registros.")
    return total

def acessar_assessoria_e_encontrar_frame(page: Page) -> Frame:
    """
    Navega para a seção de assessoria e encontra o frame que contém o botão de pesquisa.
    """
    print("[🔁] Acessando seção 'Assessoria - Visão Advogado'...")
    page.goto(
        ASSESSORIA_URL,
        timeout=90000,
        wait_until="domcontentloaded"
    )
    verificar_erro_tecnico(page, "acesso à tela de assessoria")

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
        verificar_erro_tecnico(frame.page, "pesquisa")
        seletor_botao = "input[type='image'][name='pesquisarPendenciaTarefaForm:btPTarefa']"

        print("    - Aguardando o botão de pesquisa...")
        frame.wait_for_selector(seletor_botao, timeout=20000)

        botao_pesquisar = frame.locator(seletor_botao).first
        try:
            botao_pesquisar.click(timeout=10000, no_wait_after=True)
        except TypeError:
            botao_pesquisar.click(timeout=10000)
        except Exception:
            botao_pesquisar.evaluate(
                """el => {
                    const event = new MouseEvent('click', {
                        bubbles: true,
                        cancelable: true,
                        view: window
                    });
                    el.dispatchEvent(event);
                }"""
            )
        verificar_erro_tecnico(frame.page, "clique em Pesquisar")

        print("[⏳] Aguardando carregamento dos registros...")
        frame.wait_for_selector(INFO_REGISTROS_SELECTOR, timeout=20000)

        print("[✅] Registros carregados com sucesso.")
        return True
    except Exception as e:
        print(f"[❌] Falha ao clicar no botão 'Pesquisar': {e}")
        return False

def extrair_numeros_do_pdf(caminho_pdf: str) -> set:
    """Extrai os números de solicitação do relatório PDF (Tarefa.pdf).

    No PDF cada número quebra em duas linhas por causa da coluna estreita
    (ex.: '2026/000006' + '1732'). Juntamos os dígitos separados por espaço/quebra
    antes de aplicar o padrão YYYY/NNNNNNNNNN.
    """
    from pypdf import PdfReader

    reader = PdfReader(caminho_pdf)
    texto = "\n".join((pagina.extract_text() or "") for pagina in reader.pages)
    texto_unido = re.sub(r"(?<=\d)\s+(?=\d)", "", texto)
    numeros = set(NUMERO_SOLICITACAO_PDF_PATTERN.findall(texto_unido))
    print(f"[📄] Relatório com {len(reader.pages)} página(s); {len(numeros)} números distintos extraídos.")
    return numeros


def baixar_relatorio_e_extrair(frame: Frame, total_esperado=None) -> set:
    """Clica em 'Imprimir Relatório', captura o PDF e devolve o conjunto de números."""
    page = frame.page
    verificar_erro_tecnico(page, "geração do relatório")

    print("[🖨️] Solicitando 'Imprimir Relatório' (PDF com todas as solicitações)...")
    frame.wait_for_selector(REPORT_LINK_SELECTOR, timeout=20000)
    link = frame.locator(REPORT_LINK_SELECTOR).first

    download_timeout = int(os.getenv("RPA_RELATORIO_DOWNLOAD_TIMEOUT_MS", "120000"))
    with page.expect_download(timeout=download_timeout) as download_info:
        try:
            link.click(no_wait_after=True)
        except Exception:
            link.evaluate("el => el.click()")
    download = download_info.value

    destino = Path(tempfile.gettempdir()) / f"onerequest_tarefa_{os.getpid()}.pdf"
    download.save_as(str(destino))
    print(f"[✅] Relatório baixado: {download.suggested_filename}")

    try:
        numeros = extrair_numeros_do_pdf(str(destino))
    finally:
        try:
            destino.unlink()
        except Exception:
            pass

    if not numeros:
        raise RuntimeError("Relatório baixado, mas nenhum número de solicitação foi extraído do PDF.")

    if total_esperado:
        if len(numeros) < total_esperado:
            raise RuntimeError(
                f"Relatório incompleto: {len(numeros)} números extraídos de "
                f"{total_esperado} informados pelo portal."
            )
        print(f"[✔️] Validação OK: {len(numeros)}/{total_esperado} (contador do portal).")

    print(f"✅ Coleta concluída. {len(numeros)} solicitações ativas encontradas no portal.")
    return numeros


def preparar_e_baixar_relatorio(portal_page: Page) -> set:
    tarefa_frame = acessar_assessoria_e_encontrar_frame(portal_page)
    if not tarefa_frame:
        raise RuntimeError("Não foi possível encontrar o frame de pesquisa.")

    if not clicar_pesquisar(tarefa_frame):
        raise RuntimeError("Não foi possível realizar a pesquisa.")

    # Recupera a referência do frame: o postback do Pesquisar pode tê-lo recriado.
    tarefa_frame = acessar_frame_existente(portal_page) or tarefa_frame

    total_esperado = obter_total_registros(tarefa_frame)
    return baixar_relatorio_e_extrair(tarefa_frame, total_esperado=total_esperado)


def acessar_frame_existente(page: Page) -> Frame | None:
    """Reobtém o frame que contém o form de pendências (sem renavegar)."""
    for frame in page.frames:
        try:
            if "pesquisarPendenciaTarefaForm" in frame.content():
                return frame
        except Exception:
            continue
    return None


def coletar_numeros_com_recuperacao(portal_page: Page):
    max_recuperacoes = int(os.getenv("RPA_COLETA_NUMEROS_MAX_RECUPERACOES", "5"))
    ultimo_erro = None

    for tentativa in range(1, max_recuperacoes + 1):
        try:
            if tentativa > 1:
                print(f"\n[🔁] Retomando coleta ({tentativa}/{max_recuperacoes})...")
            return preparar_e_baixar_relatorio(portal_page)

        except ErroTecnicoPortal as exc:
            ultimo_erro = exc
            print(f"[⚠️] {exc}")
            print("    - Limpando cookie problemático e voltando para a lista...")
            limpar_cookie_erro_wfj(portal_page.context)
            time.sleep(2)
            try:
                portal_page.goto(ASSESSORIA_URL, timeout=90000, wait_until="domcontentloaded")
            except Exception:
                pass
            continue

        except Exception as exc:
            # Falhas transitórias (timeout no Pesquisar, download, etc.): renavega e tenta de novo.
            ultimo_erro = exc
            print(f"[⚠️] Falha na coleta (tentativa {tentativa}/{max_recuperacoes}): {exc}")
            if tentativa < max_recuperacoes:
                time.sleep(3)
                try:
                    portal_page.goto(ASSESSORIA_URL, timeout=90000, wait_until="domcontentloaded")
                except Exception:
                    pass
                continue

    raise RuntimeError(
        f"Não foi possível concluir a coleta de números após {max_recuperacoes} tentativas. "
        f"Último erro: {ultimo_erro}"
    )

def main():
    """
    Função principal que orquestra a coleta de números e a sincronização de status.
    """
    database.inicializar_banco()

    browser_process = None
    exit_code = 0
    lock = LockChrome()
    try:
        # Uso exclusivo do Chrome: aguarda caso outro robo esteja usando (evita conflito na porta 9222).
        lock.acquire()
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

            numeros_atuais_portal = coletar_numeros_com_recuperacao(portal_page)

            # --- Sincronização via API ---
            print("\n[🔄] Sincronizando status das solicitações com o servidor...")
            resultado = database.sincronizar_portal(numeros_atuais_portal)
            print(f"✅ Sincronização concluída: {resultado.get('respondidas', 0)} marcadas como respondidas, {resultado.get('total_portal', 0)} ativas no portal.")
            
    except Exception as e:
        exit_code = 1
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

        # Libera o lock para o proximo robo, sempre.
        lock.release()
        print("--- Rotina de fechamento concluída. Fim da execução. ---")

    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
