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
    # ... (lógica de filtros e KPIs existente, sem alterações)
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
    
    conn = sqlite3.connect(database.DB_SOLICITACOES)
    conn.row_factory = sqlite3.Row
    solicitacoes = conn.execute("SELECT * FROM solicitacoes WHERE status_sistema = 'Aberto'").fetchall()
    conn.close()
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    headers = ["Recebido Em", "Nº Solicitação", "Nº Processo", "Prazo", "Polo", "Responsável", "Anotação", "Status"]
    sheet.append(headers)
    for item in solicitacoes:
        sheet.append([item['recebido_em'], item['numero_solicitacao'], item['numero_processo'], item['prazo'], item['polo'], item['responsavel'], item['anotacao'], item['status']])
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return Response(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment;filename=solicitacoes_pendentes.xlsx"})

@app.route('/exportar/json')
@login_required
def exportar_json():
    """Busca as solicitações abertas e retorna como um arquivo JSON."""
    conn = sqlite3.connect(database.DB_SOLICITACOES)
    conn.row_factory = sqlite3.Row
    # Seleciona todas as solicitações com status 'Aberto'
    solicitacoes_raw = conn.execute("SELECT * FROM solicitacoes WHERE status_sistema = 'Aberto'").fetchall()
    conn.close()

    # Converte os resultados do banco de dados (que são do tipo Row) para uma lista de dicionários
    solicitacoes_list = [dict(row) for row in solicitacoes_raw]

    # Converte a lista para uma string JSON formatada
    json_output = json.dumps(solicitacoes_list, indent=4, ensure_ascii=False)

    # Cria uma resposta Flask com o conteúdo JSON
    return Response(
        json_output,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=solicitacoes_pendentes.json"}
    )




# --- Rota de API para Gráfico (ATUALIZADA) ---
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
    #...
    dados = request.json
    database.atualizar_campos_edicao(dados.get('numero_solicitacao'), dados.get('responsavel'), dados.get('anotacao'), dados.get('status'))
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

if __name__ == '__main__':
    if not os.path.exists('templates'): os.makedirs('templates')
    database.inicializar_banco()
    if not database.obter_todos_usuarios():
        database.criar_usuario(name='admin', password='admin', role='admin')
    app.run(host='0.0.0.0', port=5000, debug=True)