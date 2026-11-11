from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import os
from bd import database
from werkzeug.security import check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import openpyxl
from io import BytesIO
import json
import re
import requests
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken

app = Flask(__name__)


# ============================================================
# PARSER DE SESSÃO MANUAL (cURL / Cookie header / JSON)
# ============================================================

def _cookies_do_cabecalho(cabecalho):
    cookies = []
    for parte in cabecalho.split(";"):
        nome, sep, valor = parte.strip().partition("=")
        if sep and nome.strip():
            cookies.append({"name": nome.strip(), "value": valor.strip(),
                            "domain": ".bb.com.br", "path": "/",
                            "secure": True, "httpOnly": True})
    return cookies


def _parse_curl(texto):
    texto = texto.replace("^\n", " ").replace("\\\n", " ").replace("\\\r\n", " ")
    if '^"' in texto:
        texto = re.sub(r"\^(.)", r"\1", texto)
    cookie = re.search(r"""(?:-b|--cookie)\s+(['"])(.*?)\1""", texto, re.S)
    cabecalho = re.search(r"""(['"])cookie:\s*(.*?)\1""", texto, re.I | re.S)
    agente = re.search(r"""(['"])user-agent:\s*(.*?)\1""", texto, re.I | re.S)
    url_match = re.search(r"""curl\s+(?:-X\s+\w+\s+)?(['"])(https?://[^'"]+)\1""", texto, re.I)
    if url_match and "bb.com.br" not in url_match.group(2):
        raise ValueError("A requisição copiada não é do portal do BB (bb.com.br).")
    bruto = (cookie and cookie.group(2)) or (cabecalho and cabecalho.group(2)) or ""
    cookies = _cookies_do_cabecalho(bruto)
    return {"cookies": cookies, "user_agent": agente.group(2).strip() if agente else None}


def _parse_json_cookies(texto):
    try:
        dado = json.loads(texto)
    except ValueError as exc:
        raise ValueError(f"O texto parece JSON, mas não abre: {exc}")
    if isinstance(dado, dict):
        lista = dado.get("cookies") or []
        agente = dado.get("user_agent")
    elif isinstance(dado, list):
        lista, agente = dado, None
    else:
        raise ValueError("Formato JSON não reconhecido.")
    cookies = []
    for c in lista:
        if isinstance(c, dict) and c.get("name") and c.get("value") is not None:
            dominio = str(c.get("domain") or ".bb.com.br")
            if "bb.com.br" not in dominio:
                continue
            cookies.append({"name": c["name"], "value": str(c["value"]),
                            "domain": dominio, "path": c.get("path") or "/",
                            "secure": bool(c.get("secure", True)),
                            "httpOnly": bool(c.get("httpOnly", True))})
    return {"cookies": cookies, "user_agent": agente}


def interpretar_sessao_manual(texto):
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("Cole o cURL ou cookies do portal do BB.")
    if texto[0] in "[{":
        sessao = _parse_json_cookies(texto)
    elif texto.lower().startswith("curl"):
        sessao = _parse_curl(texto)
    else:
        limpo = re.sub(r"(?i)^cookie:\s*", "", texto)
        sessao = {"cookies": _cookies_do_cabecalho(limpo), "user_agent": None}
    if not sessao["cookies"]:
        raise ValueError("Não encontrei cookies do BB no texto colado. "
                         "Copie uma requisição feita ao juridico.bb.com.br depois de entrar no portal.")
    return sessao


# Os cookies colados SÃO a sessão do BB de quem colou: com eles, qualquer um
# entra no portal jurídico em nome dessa chave até a sessão cair. Por isso
# ficam cifrados no banco (Fernet, chave derivada do SECRET_KEY, como no Flow):
# o banco do OneRequest não é isolado — o Flow lê este Postgres para espelhar
# as DMIs. Só o servidor decifra, na hora de entregar ao robô pela API.
def _cifra_sessao():
    chave = hashlib.sha256(f"sessao-manual-bb:{app.secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(chave))


def _cifrar_cookies(cookies):
    return _cifra_sessao().encrypt(json.dumps(cookies).encode()).decode()


def _decifrar_cookies(cifrado):
    """None quando não abre (SECRET_KEY trocou, ou registro gravado sem cifra)."""
    try:
        return json.loads(_cifra_sessao().decrypt(cifrado.encode()).decode())
    except (InvalidToken, ValueError, TypeError, AttributeError):
        return None


def carregar_env_local():
    """Carrega .env local sem depender de python-dotenv."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_key = key.strip()
            env_value = value.strip().strip('"').strip("'")
            if env_key.startswith("TWOTASK_"):
                os.environ[env_key] = env_value
            else:
                os.environ.setdefault(env_key, env_value)


carregar_env_local()

app.secret_key = os.environ.get('SECRET_KEY', 'troque-esta-chave-secreta-em-producao')

# --- Configuração do Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return database.User.get(user_id)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash("Você não tem permissão para acessar esta página.", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# --- Autenticação RPA (API Key) ---
def rpa_auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        expected_key = os.environ.get('RPA_API_KEY')
        if not expected_key or api_key != expected_key:
            return jsonify({'status': 'erro', 'mensagem': 'API key inválida ou ausente.'}), 401
        return f(*args, **kwargs)
    return decorated_function

# --- FUNÇÃO HELPER (Formatação CNJ) ---
def formatar_numero_processo_cnj(numero_str):
    if not numero_str:
        return numero_str
    numeros = re.sub(r'\D', '', numero_str)
    if len(numeros) == 20:
        return f"{numeros[0:7]}-{numeros[7:9]}.{numeros[9:13]}.{numeros[13:14]}.{numeros[14:16]}.{numeros[16:20]}"
    return numero_str


# ============================================================
# ROTAS DE AUTENTICAÇÃO
# ============================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        user = database.obter_usuario_por_nome(request.form['name'])
        if user and check_password_hash(user.password_hash, request.form['password']):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha inválidos.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ============================================================
# ROTAS DO PAINEL
# ============================================================

@app.route('/')
@login_required
def index():
    filters = {
        'responsavel': request.args.get('responsavel', ''),
        'busca': request.args.get('busca', ''),
        'data_inicio_grafico': request.args.get('data_inicio_grafico', (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')),
        'data_fim_grafico': request.args.get('data_fim_grafico', datetime.now().strftime('%Y-%m-%d'))
    }

    solicitacoes_raw = database.obter_solicitacoes_por_status(
        'Aberto',
        responsavel=filters['responsavel'] or None,
        busca=filters['busca'] or None
    )

    kpis = {'vencidas': 0, 'hoje': 0, 'amanha': 0, 'futuras': 0, 'fds': 0}
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    solicitacoes_processadas = []

    for item_raw in solicitacoes_raw:
        item = dict(item_raw)

        try:
            data_obj = datetime.strptime(item['data_agendamento'], '%d/%m/%Y').date()
            item['data_agendamento'] = data_obj.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            pass

        try:
            prazo_date = datetime.strptime(item['prazo'], '%d/%m/%Y').date()
            item['prazo_date'] = prazo_date
            dia_semana = prazo_date.weekday()

            if prazo_date < today:
                kpis['vencidas'] += 1
                item['farol_status'] = 'cinza'
            elif prazo_date == today:
                kpis['hoje'] += 1
                item['farol_status'] = 'vermelho'
            elif prazo_date == tomorrow:
                kpis['amanha'] += 1
                item['farol_status'] = 'amarelo'
            else:
                if dia_semana == 5 or dia_semana == 6:
                    kpis['fds'] += 1
                    item['farol_status'] = 'roxo'
                else:
                    kpis['futuras'] += 1
                    item['farol_status'] = 'verde'

        except (ValueError, TypeError):
            item['prazo_date'] = datetime.max.date()
            item['farol_status'] = 'cinza'

        solicitacoes_processadas.append(item)

    solicitacoes = sorted(solicitacoes_processadas, key=lambda x: x['prazo_date'])
    usuarios_dropdown = database.obter_usuarios_legal_one()

    return render_template('index.html', solicitacoes=solicitacoes, usuarios=usuarios_dropdown, kpis=kpis, filters=filters)

@app.route('/respondidas')
@login_required
def respondidas():
    solicitacoes = database.obter_solicitacoes_por_status('Respondido')
    return render_template('respondidas.html', solicitacoes=solicitacoes)

@app.route('/exportar')
@login_required
def exportar():
    solicitacoes_raw = database.obter_solicitacoes_por_status('Aberto')

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    headers = ["Recebido Em", "Nº Solicitação", "Nº Processo", "Prazo", "Polo", "Responsável", "Setor", "Data p/ agendamento", "Anotação", "Status"]
    sheet.append(headers)

    for item_raw in solicitacoes_raw:
        item = dict(item_raw)

        try:
            data_obj = datetime.strptime(item['data_agendamento'], '%Y-%m-%d').date()
            item['data_agendamento'] = data_obj.strftime('%d/%m/%Y')
        except (ValueError, TypeError):
            pass

        numero_processo_formatado = formatar_numero_processo_cnj(item['numero_processo'])

        sheet.append([
            item['recebido_em'],
            item['numero_solicitacao'],
            numero_processo_formatado,
            item['prazo'],
            item['polo'],
            item['responsavel'],
            item['setor'],
            item['data_agendamento'],
            item['anotacao'],
            item['status']
        ])

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return Response(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment;filename=solicitacoes_pendentes.xlsx"})

@app.route('/exportar/json')
@login_required
def exportar_json():
    try:
        user_map = database.obter_mapa_usuarios_id()
    except Exception as e:
        print(f"Alerta: Não foi possível carregar o mapa de usuários: {e}")
        user_map = {}

    solicitacoes_raw = database.obter_solicitacoes_por_status('Aberto')

    processos_list = []
    for row in solicitacoes_raw:
        item = dict(row)

        data_agendamento_formatada = item['data_agendamento']
        try:
            data_obj = datetime.strptime(item['data_agendamento'], '%Y-%m-%d').date()
            data_agendamento_formatada = data_obj.strftime('%d/%m/%Y')
        except (ValueError, TypeError):
            pass

        responsavel_name = item.get('responsavel')
        id_responsavel = user_map.get(responsavel_name)

        processo = {
            "id": item['id'],
            "numero_solicitacao": item['numero_solicitacao'],
            "titulo": item['titulo'],
            "npj_direcionador": item['npj_direcionador'],
            "vencimento": item['prazo'],
            "texto_dmi": item['texto_dmi'],
            "numero_processo": formatar_numero_processo_cnj(item['numero_processo']),
            "polo": item['polo'],
            "recebido_em": item['recebido_em'],
            "id_responsavel": id_responsavel,
            "anotacao": item['anotacao'],
            "status": item['status'],
            "status_sistema": item['status_sistema'],
            "setor": item['setor'],
            "prazo": data_agendamento_formatada
        }
        processos_list.append(processo)

    output_data = {
        "fonte": "OneRequest",
        "processos": processos_list
    }

    json_output = json.dumps(output_data, indent=4, ensure_ascii=False)

    return Response(
        json_output,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=solicitacoes_onerequest.json"}
    )


# ============================================================
# ROTAS DE API (Dashboard)
# ============================================================

@app.route('/api/recebimentos')
@login_required
def api_recebimentos():
    hoje = datetime.now()
    data_fim_str = request.args.get('fim', hoje.strftime('%Y-%m-%d'))
    data_inicio_str = request.args.get('inicio', (hoje - timedelta(days=14)).strftime('%Y-%m-%d'))

    try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d')
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({'erro': 'Formato de data inválido. Use AAAA-MM-DD.'}), 400

    datas_recebimento_raw = database.obter_recebimentos_por_periodo(
        data_inicio.strftime('%Y-%m-%d'),
        data_fim.strftime('%Y-%m-%d')
    )

    datas_contagem = {}
    delta = data_fim - data_inicio
    for i in range(delta.days + 1):
        data = data_inicio + timedelta(days=i)
        datas_contagem[data.strftime('%d/%m')] = 0

    total_periodo = 0
    for row in datas_recebimento_raw:
        data_recebimento = datetime.strptime(row['recebido_em'], '%Y-%m-%d %H:%M:%S')
        chave = data_recebimento.strftime('%d/%m')
        if chave in datas_contagem:
            datas_contagem[chave] += 1
        total_periodo += 1

    return jsonify({
        'labels': list(datas_contagem.keys()),
        'data': list(datas_contagem.values()),
        'total': total_periodo
    })

@app.route('/atualizar', methods=['POST'])
@login_required
def atualizar():
    dados = request.json
    database.atualizar_campos_edicao(
        dados.get('numero_solicitacao'),
        dados.get('responsavel'),
        dados.get('status'),
        dados.get('setor'),
        dados.get('data_agendamento')
    )
    return jsonify({'status': 'sucesso'})

@app.route('/api/atualizar-anotacao', methods=['POST'])
@login_required
def api_atualizar_anotacao():
    dados = request.json
    num_solicitacao = dados.get('numero_solicitacao')
    anotacao = dados.get('anotacao')

    if not num_solicitacao:
        return jsonify({'status': 'erro', 'mensagem': 'ID da solicitação não fornecido.'}), 400

    try:
        database.atualizar_anotacao(num_solicitacao, anotacao)
        return jsonify({'status': 'sucesso'})
    except Exception as e:
        print(f"Erro ao salvar anotação: {e}")
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500


# ============================================================
# ROTAS DE USUÁRIOS
# ============================================================

@app.route('/usuarios')
@login_required
@admin_required
def listar_usuarios():
    return render_template('usuarios.html', usuarios=database.obter_todos_usuarios())

@app.route('/usuarios/novo', methods=['GET', 'POST'])
@login_required
@admin_required
def novo_usuario():
    if request.method == 'POST':
        database.criar_usuario(request.form['name'], request.form['password'], request.form['role'])
        flash(f"Usuário '{request.form['name']}' criado!", 'success')
        return redirect(url_for('listar_usuarios'))
    return render_template('form_usuario.html', titulo="Novo Usuário", usuario=None)

@app.route('/usuarios/editar/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_usuario(user_id):
    usuario = database.obter_usuario_por_id(user_id)
    if request.method == 'POST':
        database.atualizar_usuario(user_id, request.form['name'], request.form['role'], new_password=request.form.get('password'))
        flash(f"Usuário '{request.form['name']}' atualizado!", 'success')
        return redirect(url_for('listar_usuarios'))
    return render_template('form_usuario.html', titulo="Editar Usuário", usuario=usuario)

@app.route('/usuarios/deletar', methods=['POST'])
@login_required
@admin_required
def deletar_usuario_action():
    user_id = request.form['user_id']
    if int(user_id) == 1:
        flash('Não é possível deletar o admin principal.', 'danger')
    else:
        database.deletar_usuario(user_id)
        flash('Usuário deletado.', 'success')
    return redirect(url_for('listar_usuarios'))


# ============================================================
# ROTA API "CRIAR TAREFA" (External TwoTask)
# ============================================================

@app.route('/api/criar-tarefa', methods=['POST'])
@login_required
def api_criar_tarefa():
    dados = request.json
    solicitacao_id = dados.get('numero_solicitacao')
    if not solicitacao_id:
        return jsonify({'status': 'erro', 'mensagem': 'Nenhum ID de solicitação fornecido.'}), 400

    try:
        user_map = database.obter_mapa_usuarios_id()
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': f'Erro ao buscar mapa de usuários: {e}'}), 500

    solicitacao_raw = database.obter_solicitacao_por_numero(solicitacao_id)

    if not solicitacao_raw:
        return jsonify({'status': 'erro', 'mensagem': 'Solicitação não encontrada.'}), 404

    item = dict(solicitacao_raw)

    data_agendamento_formatada = item['data_agendamento']
    try:
        data_obj = datetime.strptime(item['data_agendamento'], '%Y-%m-%d').date()
        data_agendamento_formatada = data_obj.strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        pass

    if not item['data_agendamento']:
        return jsonify({'status': 'erro', 'mensagem': "O campo 'Data p/ agendamento' (prazo) é obrigatório para enviar à API."}), 400

    responsavel_name = item.get('responsavel')
    id_responsavel = user_map.get(responsavel_name)

    processo = {
        "id": item['id'],
        "numero_solicitacao": item['numero_solicitacao'],
        "titulo": item['titulo'],
        "npj_direcionador": item['npj_direcionador'],
        "vencimento": item['prazo'],
        "texto_dmi": item['texto_dmi'],
        "numero_processo": formatar_numero_processo_cnj(item['numero_processo']),
        "polo": item['polo'],
        "recebido_em": item['recebido_em'],
        "id_responsavel": id_responsavel,
        "anotacao": item['anotacao'],
        "status": item['status'],
        "status_sistema": item['status_sistema'],
        "setor": item['setor'],
        "prazo": data_agendamento_formatada
    }

    output_data = {
        "fonte": "OneRequest",
        "processos": [processo]
    }

    API_URL = os.getenv("TWOTASK_BATCH_CREATE_URL", "https://flow.mdradvocacia.com/api/v1/tasks/batch-create")
    api_key = (os.getenv("TWOTASK_BATCH_API_KEY") or "").strip()
    if not api_key:
        return jsonify({'status': 'erro', 'mensagem': 'TWOTASK_BATCH_API_KEY não configurada no .env do OneRequest.'}), 500
    headers = {"X-Batch-Api-Key": api_key}

    try:
        response = requests.post(API_URL, json=output_data, headers=headers, timeout=10)

        if response.status_code in [200, 201, 202]:
            msg_sucesso = "Tarefa criada com sucesso!"
            try:
                msg_sucesso = response.json().get('message', msg_sucesso)
            except requests.exceptions.JSONDecodeError:
                pass
            return jsonify({'status': 'sucesso', 'mensagem': msg_sucesso})
        else:
            return jsonify({'status': 'erro', 'mensagem': f'API respondeu com erro {response.status_code}: {response.text}'}), 500

    except requests.exceptions.ConnectionError:
        return jsonify({'status': 'erro', 'mensagem': f'Não foi possível conectar à API em {API_URL}. Verifique a rede/VPN.'}), 500
    except requests.exceptions.Timeout:
        return jsonify({'status': 'erro', 'mensagem': 'A API demorou para responder (Timeout).'}), 500
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': f'Ocorreu um erro inesperado: {e}'}), 500


# ============================================================
# ROTAS API PARA RPA (comunicação com robôs remotos)
# ============================================================

@app.route('/api/rpa/health', methods=['GET'])
def rpa_health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

@app.route('/api/rpa/solicitacoes/abertas', methods=['GET'])
@rpa_auth_required
def rpa_obter_abertas():
    numeros = database.obter_solicitacoes_abertas_db()
    return jsonify({'numeros': numeros})

@app.route('/api/rpa/solicitacoes/sync', methods=['POST'])
@rpa_auth_required
def rpa_sync_solicitacoes():
    dados = request.json
    numeros_portal = dados.get('numeros_portal', [])

    if not numeros_portal:
        return jsonify({'status': 'erro', 'mensagem': 'Lista de números do portal vazia.'}), 400

    numeros_portal_set = set(numeros_portal)
    # obter_solicitacoes_abertas_db() ja exclui fantasmas, e marcar_como_abertas()
    # nao reabre fantasmas — entao solicitacoes marcadas como fantasma ficam fora do
    # ciclo sem tratamento especial aqui.
    numeros_abertos_db = set(database.obter_solicitacoes_abertas_db())

    respondidas = list(numeros_abertos_db - numeros_portal_set)
    if respondidas:
        database.marcar_como_respondidas(respondidas)

    database.inserir_novas_solicitacoes(list(numeros_portal_set))
    database.marcar_como_abertas(list(numeros_portal_set))

    return jsonify({
        'status': 'sucesso',
        'respondidas': len(respondidas),
        'total_portal': len(numeros_portal_set)
    })

@app.route('/api/rpa/solicitacoes/pendentes', methods=['GET'])
@rpa_auth_required
def rpa_obter_pendentes():
    pendentes = database.obter_solicitacoes_pendentes()
    return jsonify({'numeros': pendentes})

@app.route('/api/rpa/solicitacoes/detalhes', methods=['PUT'])
@rpa_auth_required
def rpa_atualizar_detalhes():
    dados = request.json
    if not dados.get('numero_solicitacao'):
        return jsonify({'status': 'erro', 'mensagem': 'numero_solicitacao é obrigatório.'}), 400

    database.atualizar_detalhes_solicitacao(dados)
    return jsonify({'status': 'sucesso'})

@app.route('/api/rpa/solicitacoes/vencem-hoje', methods=['GET'])
@rpa_auth_required
def rpa_obter_vencem_hoje():
    return jsonify({'numeros': database.obter_solicitacoes_vencem_hoje()})

@app.route('/api/rpa/solicitacoes/atrasadas', methods=['GET'])
@rpa_auth_required
def rpa_obter_atrasadas():
    return jsonify({'numeros': database.obter_solicitacoes_atrasadas()})

@app.route('/api/rpa/solicitacoes/status-portal', methods=['PUT'])
@rpa_auth_required
def rpa_atualizar_status_portal():
    dados = request.json
    numero = dados.get('numero_solicitacao')
    if not numero:
        return jsonify({'status': 'erro', 'mensagem': 'numero_solicitacao é obrigatório.'}), 400
    database.atualizar_status_portal(
        numero,
        dados.get('status_portal'),
        tem_anotacao_portal=dados.get('tem_anotacao_portal'),
    )
    return jsonify({'status': 'sucesso'})


@app.route('/api/rpa/solicitacoes/fantasma', methods=['PUT'])
@rpa_auth_required
def rpa_marcar_fantasma():
    """Liga/desliga o flag fantasma de uma solicitação (descarte do fluxo).

    Body: { "numero_solicitacao": "AAAA/NNNNNNNNNN", "fantasma": true|false }
    'fantasma' é opcional e assume True quando ausente.
    """
    dados = request.json or {}
    numero = dados.get('numero_solicitacao')
    if not numero:
        return jsonify({'status': 'erro', 'mensagem': 'numero_solicitacao é obrigatório.'}), 400
    valor = bool(dados.get('fantasma', True))
    database.marcar_como_fantasma([numero], valor)
    return jsonify({'status': 'sucesso', 'numero_solicitacao': numero, 'fantasma': valor})


@app.route('/api/rpa/solicitacoes/fantasmas', methods=['GET'])
@rpa_auth_required
def rpa_listar_fantasmas():
    return jsonify({'numeros': database.obter_solicitacoes_fantasma()})


# ============================================================
# ROTAS DA SESSÃO MANUAL BB (Dashboard)
# ============================================================

@app.route('/sessao-manual')
@login_required
@admin_required
def sessao_manual_page():
    estado = database.estado_sessao_manual()
    return render_template('sessao_manual.html', estado=estado)


@app.route('/sessao-manual/colar', methods=['POST'])
@login_required
@admin_required
def sessao_manual_colar():
    texto = request.form.get('texto', '')
    try:
        sessao = interpretar_sessao_manual(texto)
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('sessao_manual_page'))
    database.guardar_sessao_manual(
        cookies_json=_cifrar_cookies(sessao['cookies']),
        user_agent=sessao.get('user_agent'),
        criado_por=current_user.name,
    )
    flash(f"Sessão recebida ({len(sessao['cookies'])} cookies). "
          f"Válida por {database.SESSAO_MANUAL_VALIDADE_HORAS}h.", 'success')
    return redirect(url_for('sessao_manual_page'))


@app.route('/sessao-manual/descartar', methods=['POST'])
@login_required
@admin_required
def sessao_manual_descartar():
    database.descartar_sessao_manual()
    flash("Sessão manual descartada. Os robôs voltam a usar o OneLog.", 'warning')
    return redirect(url_for('sessao_manual_page'))


# ============================================================
# ROTAS DA SESSÃO MANUAL BB (API para RPAs)
# ============================================================

@app.route('/api/rpa/sessao-manual', methods=['GET'])
@rpa_auth_required
def rpa_obter_sessao_manual():
    row = database.obter_sessao_manual_vigente()
    if not row:
        return jsonify({'ativa': False})
    cookies = _decifrar_cookies(row['cookies_json'])
    if cookies is None:
        database.invalidar_sessao_manual(
            "Os cookies guardados não abrem (o SECRET_KEY do servidor mudou?). Cole a sessão de novo.",
            row['id'],
        )
        return jsonify({'ativa': False})
    return jsonify({
        'ativa': True,
        # O robô devolve o id ao invalidar: só ESTA sessão sai de uso.
        'id': row['id'],
        'cookies': cookies,
        'user_agent': row['user_agent'],
        'criado_por': row['criado_por'],
    })


@app.route('/api/rpa/sessao-manual/invalidar', methods=['PUT'])
@rpa_auth_required
def rpa_invalidar_sessao_manual():
    dados = request.get_json(silent=True) or {}
    motivo = str(dados.get('motivo') or 'Invalidada pelo RPA')[:500]
    sessao_id = dados.get('id')
    if sessao_id is not None:
        try:
            sessao_id = int(sessao_id)
        except (TypeError, ValueError):
            return jsonify({'status': 'erro', 'mensagem': 'id da sessão inválido.'}), 400
    # Com id, só aquela sessão sai de uso (a que o robô testou); sem id
    # (robô anterior a esta versão), a vigente.
    database.invalidar_sessao_manual(motivo, sessao_id)
    return jsonify({'status': 'sucesso'})


# ============================================================
# INICIALIZAÇÃO
# ============================================================

if __name__ == '__main__':
    if not os.path.exists('templates'):
        os.makedirs('templates')
    database.inicializar_banco()
    if not database.obter_todos_usuarios():
        database.criar_usuario(name='admin', password='admin', role='admin')
    app.run(host='0.0.0.0', port=5000, debug=True)
