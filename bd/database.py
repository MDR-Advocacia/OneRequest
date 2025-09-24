import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

# --- Configuração dos Caminhos ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_SOLICITACOES = os.path.join(BASE_DIR, "solicitacoes.db")
DB_LEGAL_ONE = os.path.join(BASE_DIR, "database.db") 

def conectar(db_file):
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    return conn

class User(UserMixin):
    # ... (código existente, sem alterações)
    def __init__(self, id, name, password_hash, role):
        self.id = id
        self.name = name
        self.password_hash = password_hash
        self.role = role
    @staticmethod
    def get(user_id):
        conn = conectar(DB_SOLICITACOES)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
        user_data = cursor.fetchone()
        conn.close()
        if user_data:
            return User(user_data['id'], user_data['name'], user_data['password_hash'], user_data['role'])
        return None

def inicializar_banco():
    """Inicializa o banco de dados, criando/atualizando as tabelas."""
    conn = conectar(DB_SOLICITACOES)
    cursor = conn.cursor()
    # Tabela de solicitações com a nova coluna 'status_sistema'
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS solicitacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, numero_solicitacao TEXT UNIQUE NOT NULL, titulo TEXT,
        npj_direcionador TEXT, prazo TEXT, texto_dmi TEXT, numero_processo TEXT, polo TEXT,
        recebido_em TEXT, responsavel TEXT DEFAULT 'N/A', anotacao TEXT DEFAULT '', 
        status TEXT DEFAULT 'Não',
        status_sistema TEXT DEFAULT 'Aberto' NOT NULL 
    );
    """)
    # Adiciona a coluna se ela não existir (para bancos de dados antigos)
    try:
        cursor.execute("ALTER TABLE solicitacoes ADD COLUMN status_sistema TEXT DEFAULT 'Aberto' NOT NULL;")
        conn.commit()
    except sqlite3.OperationalError:
        pass # Coluna já existe
    
    # Tabela de usuários (sem alteração)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL, role TEXT DEFAULT 'user' NOT NULL
    );
    """)
    conn.commit()
    conn.close()

# --- Funções para Sincronização de Status ---
def obter_solicitacoes_abertas_db():
    """Retorna uma lista de todos os números de solicitação marcados como 'Aberto'."""
    conn = conectar(DB_SOLICITACOES)
    cursor = conn.cursor()
    cursor.execute("SELECT numero_solicitacao FROM solicitacoes WHERE status_sistema = 'Aberto'")
    solicitacoes = [row['numero_solicitacao'] for row in cursor.fetchall()]
    conn.close()
    return solicitacoes

def marcar_como_respondidas(numeros_solicitacao):
    """Atualiza o status_sistema de uma lista de solicitações para 'Respondido'."""
    if not numeros_solicitacao:
        return
    conn = conectar(DB_SOLICITACOES)
    cursor = conn.cursor()
    # Prepara uma lista de tuplas para a atualização em massa
    dados_para_atualizar = [(numero,) for numero in numeros_solicitacao]
    cursor.executemany("UPDATE solicitacoes SET status_sistema = 'Respondido' WHERE numero_solicitacao = ?", dados_para_atualizar)
    conn.commit()
    conn.close()

# --- O restante do arquivo (funções de CRUD, etc.) permanece o mesmo ---
def criar_usuario(name, password, role):
    conn = conectar(DB_SOLICITACOES)
    cursor = conn.cursor()
    password_hash = generate_password_hash(password)
    try:
        cursor.execute("INSERT INTO usuarios (name, password_hash, role) VALUES (?, ?, ?)", (name, password_hash, role))
        conn.commit()
    except sqlite3.IntegrityError:
        print(f"Erro: Nome de usuário '{name}' já cadastrado.")
    finally:
        conn.close()

def obter_usuario_por_nome(name):
    conn = conectar(DB_SOLICITACOES)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE name = ?", (name,))
    user_data = cursor.fetchone()
    conn.close()
    if user_data:
        return User(user_data['id'], user_data['name'], user_data['password_hash'], user_data['role'])
    return None

def obter_todos_usuarios():
    conn = conectar(DB_SOLICITACOES)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios ORDER BY name ASC;")
    usuarios = cursor.fetchall()
    conn.close()
    return usuarios

def obter_usuario_por_id(user_id):
    conn = conectar(DB_SOLICITACOES)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    usuario = cursor.fetchone()
    conn.close()
    return usuario

def atualizar_usuario(user_id, name, role, new_password=None):
    conn = conectar(DB_SOLICITACOES)
    cursor = conn.cursor()
    if new_password:
        password_hash = generate_password_hash(new_password)
        cursor.execute("UPDATE usuarios SET name = ?, role = ?, password_hash = ? WHERE id = ?", (name, role, password_hash, user_id))
    else:
        cursor.execute("UPDATE usuarios SET name = ?, role = ? WHERE id = ?", (name, role, user_id))
    conn.commit()
    conn.close()

def deletar_usuario(user_id):
    conn = conectar(DB_SOLICITACOES)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    
def inserir_novas_solicitacoes(numeros_solicitacao):
    conn = conectar(DB_SOLICITACOES)
    cursor = conn.cursor()
    timestamp_atual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    dados_para_inserir = [(numero, timestamp_atual) for numero in numeros_solicitacao]
    cursor.executemany("INSERT OR IGNORE INTO solicitacoes (numero_solicitacao, recebido_em) VALUES (?, ?);", dados_para_inserir)
    conn.commit()
    conn.close()

def atualizar_detalhes_solicitacao(dados_solicitacao):
    conn = conectar(DB_SOLICITACOES)
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE solicitacoes SET titulo = ?, npj_direcionador = ?, prazo = ?, texto_dmi = ?, numero_processo = ?, polo = ? WHERE numero_solicitacao = ?;
    """, (
        dados_solicitacao.get("titulo"), dados_solicitacao.get("npj_direcionador"), dados_solicitacao.get("prazo"),
        dados_solicitacao.get("texto_dmi"), dados_solicitacao.get("numero_processo"), dados_solicitacao.get("polo"),
        dados_solicitacao.get("numero_solicitacao")
    ))
    conn.commit()
    conn.close()

def obter_solicitacoes_pendentes():
    conn = conectar(DB_SOLICITACOES)
    cursor = conn.cursor()
    cursor.execute("SELECT numero_solicitacao FROM solicitacoes WHERE titulo IS NULL;")
    pendentes = [row['numero_solicitacao'] for row in cursor.fetchall()]
    conn.close()
    return pendentes

def obter_usuarios_legal_one():
    try:
        conn = conectar(DB_LEGAL_ONE)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM legal_one_users ORDER BY name ASC;")
        usuarios = cursor.fetchall()
        conn.close()
        return usuarios
    except sqlite3.OperationalError:
        return []

def atualizar_campos_edicao(num_solicitacao, responsavel, anotacao, status):
    conn = conectar(DB_SOLICITACOES)
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE solicitacoes SET responsavel = ?, anotacao = ?, status = ? WHERE numero_solicitacao = ?;
    """, (responsavel, anotacao, status, num_solicitacao))
    conn.commit()
    conn.close()