from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import sqlite3
import os
from bd import database
from werkzeug.security import check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_super_segura_pode_ser_qualquer_coisa' 

# --- Configuração do Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, faça login para acessar esta página."
login_manager.login_message_category = "warning"

@login_manager.user_loader
def load_user(user_id):
    """Carrega o usuário para a sessão."""
    return database.User.get(user_id)

# --- Decorador de Admin ---
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
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = request.form['name']
        password = request.form['password']
        user = database.obter_usuario_por_nome(name)
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha inválidos. Tente novamente.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))

# --- Rotas Protegidas ---

@app.route('/')
@login_required
def index():
    conn_solicitacoes = sqlite3.connect(database.DB_SOLICITACOES)
    conn_solicitacoes.row_factory = sqlite3.Row
    cursor = conn_solicitacoes.cursor()
    cursor.execute("SELECT * FROM solicitacoes ORDER BY id DESC")
    solicitacoes = cursor.fetchall()
    conn_solicitacoes.close()
    usuarios_dropdown = database.obter_usuarios_legal_one()
    return render_template('index.html', solicitacoes=solicitacoes, usuarios=usuarios_dropdown)

@app.route('/atualizar', methods=['POST'])
@login_required
def atualizar():
    try:
        dados = request.json
        database.atualizar_campos_edicao(
            dados.get('numero_solicitacao'), dados.get('responsavel'),
            dados.get('anotacao'), dados.get('status')
        )
        return jsonify({'status': 'sucesso', 'mensagem': 'Solicitação atualizada com sucesso!'})
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': 'Ocorreu um erro no servidor.'}), 500

# --- Rotas CRUD para Usuários (Protegidas com @admin_required) ---

@app.route('/usuarios')
@login_required
@admin_required
def listar_usuarios():
    usuarios_sistema = database.obter_todos_usuarios()
    return render_template('usuarios.html', usuarios=usuarios_sistema)

@app.route('/usuarios/novo', methods=['GET', 'POST'])
@login_required
@admin_required
def novo_usuario():
    if request.method == 'POST':
        name = request.form['name']
        password = request.form['password']
        role = request.form['role']
        if name and password and role:
            database.criar_usuario(name, password, role)
            flash(f'Usuário "{name}" criado com sucesso!', 'success')
            return redirect(url_for('listar_usuarios'))
        else:
            flash('Todos os campos são obrigatórios.', 'danger')
    return render_template('form_usuario.html', titulo="Novo Usuário do Sistema", usuario=None)

@app.route('/usuarios/editar/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_usuario(user_id):
    usuario = database.obter_usuario_por_id(user_id)
    if not usuario:
        return "Usuário não encontrado", 404
    if request.method == 'POST':
        name = request.form['name']
        role = request.form['role']
        password = request.form.get('password')
        database.atualizar_usuario(user_id, name, role, new_password=password)
        flash(f'Usuário "{name}" atualizado com sucesso!', 'success')
        return redirect(url_for('listar_usuarios'))
    return render_template('form_usuario.html', titulo="Editar Usuário do Sistema", usuario=usuario)

@app.route('/usuarios/deletar', methods=['POST'])
@login_required
@admin_required
def deletar_usuario_action():
    user_id = request.form['user_id']
    if int(user_id) == 1:
        flash('Não é possível deletar o usuário administrador principal.', 'danger')
        return redirect(url_for('listar_usuarios'))
    database.deletar_usuario(user_id)
    flash('Usuário deletado com sucesso!', 'success')
    return redirect(url_for('listar_usuarios'))


if __name__ == '__main__':
    if not os.path.exists('templates'):
        os.makedirs('templates')
    
    # Inicializa o banco de dados para garantir que as tabelas existam
    database.inicializar_banco()


    if not database.obter_todos_usuarios():
        print("Nenhum usuário encontrado. Criando usuário 'admin' padrão...")
        # Se não existir, cria o primeiro usuário como admin
        database.criar_usuario(name='admin', password='admin', role='admin')
        print("Usuário 'admin' com senha 'admin' criado com sucesso!")

    
    print("Servidor iniciado!")
    print("Acesse a página de login em: http://127.0.0.1:5001/login")
    app.run(debug=True, port=5001)