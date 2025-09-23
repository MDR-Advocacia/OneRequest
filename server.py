from flask import Flask, render_template, request, jsonify
import sqlite3
import os

# Importa as funções do nosso módulo de bd
from bd import database

app = Flask(__name__)

# --- Rota Principal (Painel) ---
@app.route('/')
def index():
    """Busca todas as solicitações e a lista de usuários para exibir no painel."""
    conn_solicitacoes = sqlite3.connect(database.DB_SOLICITACOES)
    conn_solicitacoes.row_factory = sqlite3.Row
    cursor = conn_solicitacoes.cursor()
    cursor.execute("SELECT * FROM solicitacoes ORDER BY id DESC")
    solicitacoes = cursor.fetchall()
    conn_solicitacoes.close()

    usuarios = database.obter_usuarios_legal_one()
    
    return render_template('index.html', solicitacoes=solicitacoes, usuarios=usuarios)

# --- Rota da API para Atualizar Dados ---
@app.route('/atualizar', methods=['POST'])
def atualizar():
    """Recebe os dados do painel e atualiza o banco de dados."""
    try:
        dados = request.json
        num_solicitacao = dados.get('numero_solicitacao')
        responsavel = dados.get('responsavel')
        anotacao = dados.get('anotacao')
        status = dados.get('status')
        
        if not num_solicitacao:
            return jsonify({'status': 'erro', 'mensagem': 'Número da solicitação não fornecido.'}), 400

        database.atualizar_campos_edicao(num_solicitacao, responsavel, anotacao, status)
        
        return jsonify({'status': 'sucesso', 'mensagem': 'Solicitação atualizada com sucesso!'})
    except Exception as e:
        print(f"ERRO na rota /atualizar: {e}")
        return jsonify({'status': 'erro', 'mensagem': 'Ocorreu um erro no servidor.'}), 500

if __name__ == '__main__':
    if not os.path.exists('templates'):
        os.makedirs('templates')
        
    print("Painel pronto para ser acessado.")
    print("Acesse em seu navegador: http://127.0.0.1:5001")
    app.run(debug=True, port=5001)