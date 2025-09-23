import sqlite3
import os
from datetime import datetime

# Constrói o caminho para o arquivo do banco de dados DENTRO da pasta 'bd'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_FILE = os.path.join(BASE_DIR, "solicitacoes.db")

def conectar():
    """Cria a conexão com o banco de dados SQLite."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_banco():
    """Cria a tabela 'solicitacoes' se ela não existir, agora com a coluna 'recebido_em'."""
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS solicitacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_solicitacao TEXT UNIQUE NOT NULL,
        titulo TEXT,
        npj_direcionador TEXT,
        prazo TEXT,
        texto_dmi TEXT,
        numero_processo TEXT,
        polo TEXT,
        recebido_em TEXT
    );
    """)
    conn.commit()
    conn.close()
    print("✅ Banco de dados inicializado com sucesso em 'onerequest/bd/'.")

def inserir_novas_solicitacoes(numeros_solicitacao):
    """
    Insere novas solicitações no banco de dados com a data e hora atual.
    Ignora números que já existem, preservando a data de recebimento original.
    """
    conn = conectar()
    cursor = conn.cursor()
    
    timestamp_atual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Prepara uma lista de tuplas para inserção em massa
    dados_para_inserir = [(numero, timestamp_atual) for numero in numeros_solicitacao]
    
    # INSERT OR IGNORE garante que apenas registros novos (com base na chave UNIQUE) sejam inseridos.
    cursor.executemany("""
    INSERT OR IGNORE INTO solicitacoes (numero_solicitacao, recebido_em) VALUES (?, ?);
    """, dados_para_inserir)
    
    conn.commit()
    conn.close()

def atualizar_detalhes_solicitacao(dados_solicitacao):
    """
    Atualiza os detalhes de uma solicitação existente no banco de dados.
    Esta função NUNCA mexe na coluna 'recebido_em'.
    """
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
    UPDATE solicitacoes 
    SET 
        titulo = ?, 
        npj_direcionador = ?, 
        prazo = ?, 
        texto_dmi = ?, 
        numero_processo = ?, 
        polo = ?
    WHERE 
        numero_solicitacao = ?;
    """, (
        dados_solicitacao.get("titulo"),
        dados_solicitacao.get("npj_direcionador"),
        dados_solicitacao.get("prazo"),
        dados_solicitacao.get("texto_dmi"),
        dados_solicitacao.get("numero_processo"),
        dados_solicitacao.get("polo"),
        dados_solicitacao.get("numero_solicitacao") # A chave para o WHERE
    ))
    
    conn.commit()
    conn.close()

def obter_solicitacoes_pendentes():
    """
    Retorna uma lista de números de solicitação que ainda não foram processados.
    Consideramos "pendente" uma solicitação que não tem um título.
    """
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT numero_solicitacao FROM solicitacoes WHERE titulo IS NULL;")
    pendentes = [row['numero_solicitacao'] for row in cursor.fetchall()]
    conn.close()
    return pendentes