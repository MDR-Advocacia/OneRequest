from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import sqlite3
import os
from bd import database
from werkzeug.security import check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import openpyxl
from io import BytesIO
import json
import re 
import requests # <-- BIBLIOTECA ADICIONADA

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_super_segura_pode_ser_qualquer_coisa' 

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

# --- FUNÇÃO HELPER (Formatação CNJ) ---
def formatar_numero_processo_cnj(numero_str):
    """Formata um número de processo de 20 dígitos para o padrão CNJ."""
    if not numero_str:
        return numero_str 

    numeros = re.sub(r'\D', '', numero_str)
    
    if len(numeros) == 20:
        return f"{numeros[0:7]}-{numeros[7:9]}.{numeros[9:13]}.{numeros[13:14]}.{numeros[14:16]}.{numeros[16:20]}"
    else:
        return numero_str


# --- Rotas de Autenticação ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
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

# --- Rotas do Painel ---



@app.route('/')
@login_required
def index():
    # ROTA index() (Sem alterações)
    filters = {
        'responsavel': request.args.get('responsavel', ''),
        'busca': request.args.get('busca', ''),
        'data_inicio_grafico': request.args.get('data_inicio_grafico', (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')),
        'data_fim_grafico': request.args.get('data_fim_grafico', datetime.now().strftime('%Y-%m-%d'))
    }
    conn_solicitacoes = sqlite3.connect(database.DB_SOLICITACOES)
    conn_solicitacoes.row_factory = sqlite3.Row
    query = "SELECT * FROM solicitacoes WHERE status_sistema = 'Aberto'"
    params = []
    if filters['responsavel']:
        query += " AND responsavel = ?"
        params.append(filters['responsavel'])
    if filters['busca']:
        query += " AND (numero_solicitacao LIKE ? OR numero_processo LIKE ? OR titulo LIKE ?)"
        params.extend([f"%{filters['busca']}%", f"%{filters['busca']}%", f"%{filters['busca']}%"])
    solicitacoes_raw = conn_solicitacoes.execute(query, params).fetchall()
    conn_solicitacoes.close()
    kpis = {'vencidas': 0, 'hoje': 0, 'amanha': 0, 'futuras': 0}
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

        item['farol_status'] = 'cinza'
        try:
            prazo_date = datetime.strptime(item['prazo'], '%d/%m/%Y').date()
            item['prazo_date'] = prazo_date
            if prazo_date < today: kpis['vencidas'] += 1; item['farol_status'] = 'vermelho'
            elif prazo_date == today: kpis['hoje'] += 1; item['farol_status'] = 'amarelo'
            elif prazo_date == tomorrow: kpis['amanha'] += 1; item['farol_status'] = 'verde'
            else: kpis['futuras'] += 1; item['farol_status'] = 'verde'
        except (ValueError, TypeError):
            item['prazo_date'] = datetime.max.date()
        solicitacoes_processadas.append(item)
    
    solicitacoes = sorted(solicitacoes_processadas, key=lambda x: x['prazo_date'])
    usuarios_dropdown = database.obter_usuarios_legal_one()
    
    return render_template('index.html', solicitacoes=solicitacoes, usuarios=usuarios_dropdown, kpis=kpis, filters=filters)

@app.route('/respondidas')
@login_required
def respondidas():
    conn = sqlite3.connect(database.DB_SOLICITACOES)
    conn.row_factory = sqlite3.Row
    solicitacoes = conn.execute("SELECT * FROM solicitacoes WHERE status_sistema = 'Respondido' ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('respondidas.html', solicitacoes=solicitacoes)
    
@app.route('/exportar')
@login_required
def exportar():
    # ROTA EXPORTAR (EXCEL) (Sem alterações)
    conn = sqlite3.connect(database.DB_SOLICITACOES)
    conn.row_factory = sqlite3.Row
    solicitacoes_raw = conn.execute("SELECT * FROM solicitacoes WHERE status_sistema = 'Aberto'").fetchall()
    conn.close()
    
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
    # ROTA EXPORTAR (JSON) (Sem alterações)
    try:
        user_map = database.obter_mapa_usuarios_id()
    except Exception as e:
        print(f"Alerta: Não foi possível carregar o mapa de usuários: {e}")
        user_map = {}

    conn = sqlite3.connect(database.DB_SOLICITACOES)
    conn.row_factory = sqlite3.Row
    solicitacoes_raw = conn.execute("SELECT * FROM solicitacoes WHERE status_sistema = 'Aberto'").fetchall()
    conn.close()

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


# --- Rota de API para Gráfico ---
@app.route('/api/recebimentos')
@login_required
def api_recebimentos():
    """Calcula e retorna os dados de recebimentos para um intervalo de datas."""
    # Pega as datas dos parâmetros da URL. Usa os últimos 15 dias como padrão.
    hoje = datetime.now()
    data_fim_str = request.args.get('fim', hoje.strftime('%Y-%m-%d'))
    data_inicio_str = request.args.get('inicio', (hoje - timedelta(days=14)).strftime('%Y-%m-%d'))

    try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d')
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({'erro': 'Formato de data inválido. Use AAAA-MM-DD.'}), 400

    conn = sqlite3.connect(database.DB_SOLICITACOES)
    conn.row_factory = sqlite3.Row
    query = "SELECT recebido_em FROM solicitacoes WHERE recebido_em IS NOT NULL AND DATE(recebido_em) BETWEEN ? AND ?"
    params = (data_inicio.strftime('%Y-%m-%d'), data_fim.strftime('%Y-%m-%d'))
    datas_recebimento_raw = conn.execute(query, params).fetchall()
    conn.close()
    
    # Prepara os dados para o gráfico
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

# --- O restante do server.py (API e CRUD) permanece o mesmo ---
@app.route('/atualizar', methods=['POST'])
@login_required
def atualizar():
    # Esta rota salva o que o <input type="date"> envia (AAAA-MM-DD)
    dados = request.json
    database.atualizar_campos_edicao(
        dados.get('numero_solicitacao'), 
        dados.get('responsavel'), 
        dados.get('anotacao'), 
        dados.get('status'),
        dados.get('setor'),
        dados.get('data_agendamento')
    )
    return jsonify({'status': 'sucesso'})

@app.route('/usuarios')
@login_required
@admin_required
def listar_usuarios():
    #...
    return render_template('usuarios.html', usuarios=database.obter_todos_usuarios())

@app.route('/usuarios/novo', methods=['GET', 'POST'])
@login_required
@admin_required
def novo_usuario():
    #...
    if request.method == 'POST':
        database.criar_usuario(request.form['name'], request.form['password'], request.form['role'])
        flash(f"Usuário '{request.form['name']}' criado!", 'success')
        return redirect(url_for('listar_usuarios'))
    return render_template('form_usuario.html', titulo="Novo Usuário", usuario=None)

@app.route('/usuarios/editar/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_usuario(user_id):
    #...
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
    #...
    user_id = request.form['user_id']
    if int(user_id) == 1:
        flash('Não é possível deletar o admin principal.', 'danger')
    else:
        database.deletar_usuario(user_id)
        flash('Usuário deletado.', 'success')
    return redirect(url_for('listar_usuarios'))

# --- NOVA ROTA DE API ---
@app.route('/api/criar-tarefa', methods=['POST'])
@login_required
def api_criar_tarefa():
    # Pega o ID da solicitação enviado pelo JavaScript
    dados = request.json
    solicitacao_id = dados.get('numero_solicitacao')
    if not solicitacao_id:
        return jsonify({'status': 'erro', 'mensagem': 'Nenhum ID de solicitação fornecido.'}), 400

    # 1. Obter o mapa de usuários (Nome -> ID) do Legal One
    try:
        user_map = database.obter_mapa_usuarios_id()
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': f'Erro ao buscar mapa de usuários: {e}'}), 500

    # 2. Obter os dados completos da solicitação específica
    conn = sqlite3.connect(database.DB_SOLICITACOES)
    conn.row_factory = sqlite3.Row
    solicitacao_raw = conn.execute("SELECT * FROM solicitacoes WHERE numero_solicitacao = ?", (solicitacao_id,)).fetchone()
    conn.close()

    if not solicitacao_raw:
        return jsonify({'status': 'erro', 'mensagem': 'Solicitação não encontrada.'}), 404

    # 3. Formatar os dados da solicitação
    item = dict(solicitacao_raw)
    
    # Formata data_agendamento (AAAA-MM-DD para DD/MM/AAAA)
    data_agendamento_formatada = item['data_agendamento']
    try:
        data_obj = datetime.strptime(item['data_agendamento'], '%Y-%m-%d').date()
        data_agendamento_formatada = data_obj.strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        pass 
    
    # Busca o ID do responsável
    responsavel_name = item.get('responsavel')
    id_responsavel = user_map.get(responsavel_name) # Retorna ID ou None

    # Monta o dicionário "processo"
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

    # 4. Monta o payload final para a API (com lote de 1 item)
    output_data = {
        "fonte": "OneRequest",
        "processos": [processo] # Envia a tarefa única dentro da lista
    }

    # 5. Envia o POST para a API externa
    API_URL = "http://192.168.0.66:8000/api/v1/tasks/batch-create"
    
    try:
        response = requests.post(API_URL, json=output_data, timeout=10)
        
        # Verifica se a API respondeu com sucesso
        if response.status_code == 200 or response.status_code == 201:
            return jsonify({'status': 'sucesso', 'mensagem': 'Tarefa criada com sucesso!'})
        else:
            # Retorna o erro que a API deu
            return jsonify({'status': 'erro', 'mensagem': f'API respondeu com erro {response.status_code}: {response.text}'}), 500

    except requests.exceptions.ConnectionError:
        return jsonify({'status': 'erro', 'mensagem': f'Não foi possível conectar à API em {API_URL}. Verifique a rede/VPN.'}), 500
    except requests.exceptions.Timeout:
        return jsonify({'status': 'erro', 'mensagem': 'A API demorou para responder (Timeout).'}), 500
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': f'Ocorreu um erro inesperado: {e}'}), 500
# --- FIM DA NOVA ROTA ---


if __name__ == '__main__':
    if not os.path.exists('templates'): os.makedirs('templates')
    database.inicializar_banco()
    if not database.obter_todos_usuarios():
        database.criar_usuario(name='admin', password='admin', role='admin')
    app.run(host='0.0.0.0', port=5000, debug=True)