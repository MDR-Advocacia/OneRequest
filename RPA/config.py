from pathlib import Path

# --- CONFIGURAÇÕES DE CONEXÃO ---

# URL da sua extensão de login.
EXTENSION_URL = "chrome-extension://lnidijeaekolpfeckelhkomndglcglhh/index.html"

# Porta de depuração remota do Chrome.
CDP_ENDPOINT = "http://localhost:9222"

# --- CAMINHOS DE ARQUIVOS ---

# Caminho para o arquivo .bat que abre o Chrome.
BAT_FILE_PATH = Path(__file__).resolve().parent / "abrir_chrome.bat"

# --- URLs DA APLICAÇÃO ---

# URL base para a consulta direta de processos.
URL_BUSCA_PROCESSO = "https://juridico.bb.com.br/paj/juridico/v2?app=processoConsultaRapidoTomboApp&numeroTombo="