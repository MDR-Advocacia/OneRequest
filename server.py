from flask import Flask, render_template, g
import sqlite3
import os

# --- Configuração ---
# Aponta para o arquivo do banco de dados que está na pasta 'bd'
DATABASE = os.path.join(os.path.dirname(__file__), 'bd', 'solicitacoes.db')
app = Flask(__name__)

# --- Conexão com o Banco de Dados ---
def get_db():
    """Abre uma nova conexão com o banco de dados se não houver uma."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        # Retorna as linhas como dicionários para facilitar o uso no template
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Fecha a conexão com o banco de dados ao final da requisição."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# --- Rotas da Aplicação ---
@app.route('/')
def index():
    """Busca todas as solicitações do banco de dados e exibe no painel."""
    db = get_db()
    cursor = db.cursor()
    # Ordena pelas mais recentes primeiro
    cursor.execute("SELECT * FROM solicitacoes ORDER BY id DESC")
    solicitacoes = cursor.fetchall()
    
    # Renderiza o template HTML, passando a lista de solicitações
    return render_template('index.html', solicitacoes=solicitacoes)

if __name__ == '__main__':
    # Cria a pasta 'templates' se ela não existir
    if not os.path.exists('templates'):
        os.makedirs('templates')
        
    print("Painel pronto para ser acessado.")
    print("Acesse em seu navegador: http://127.0.0.1:5001")
    app.run(debug=True, port=5001)