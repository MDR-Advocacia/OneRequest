import os
from datetime import datetime
from contextlib import contextmanager
from werkzeug.security import generate_password_hash
from flask_login import UserMixin
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://onerequest:senha_segura@localhost:5432/onerequest"
)

_pool = None


def _get_pool():
    global _pool
    if _pool is None or _pool.closed:
        _pool = ThreadedConnectionPool(1, 10, DATABASE_URL)
    return _pool


@contextmanager
def _get_conn():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextmanager
def _get_cursor():
    with _get_conn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cur
        finally:
            cur.close()


class User(UserMixin):
    def __init__(self, id, name, password_hash, role):
        self.id = id
        self.name = name
        self.password_hash = password_hash
        self.role = role

    @staticmethod
    def get(user_id):
        with _get_cursor() as cur:
            cur.execute("SELECT * FROM usuarios WHERE id = %s", (user_id,))
            row = cur.fetchone()
        if row:
            return User(row['id'], row['name'], row['password_hash'], row['role'])
        return None


def inicializar_banco():
    with _get_cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS solicitacoes (
            id SERIAL PRIMARY KEY,
            numero_solicitacao TEXT UNIQUE NOT NULL,
            titulo TEXT,
            npj_direcionador TEXT,
            prazo TEXT,
            texto_dmi TEXT,
            numero_processo TEXT,
            polo TEXT,
            recebido_em TEXT,
            responsavel TEXT DEFAULT 'N/A',
            anotacao TEXT DEFAULT '',
            status TEXT DEFAULT 'Não',
            setor TEXT DEFAULT 'N/A',
            data_agendamento TEXT DEFAULT '',
            status_sistema TEXT DEFAULT 'Aberto' NOT NULL
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user' NOT NULL
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS legal_one_users (
            id SERIAL PRIMARY KEY,
            name TEXT,
            external_id TEXT
        );
        """)


# --- Funções de Sincronização de Status (usadas pelo RPA) ---

def obter_solicitacoes_abertas_db():
    with _get_cursor() as cur:
        cur.execute("SELECT numero_solicitacao FROM solicitacoes WHERE status_sistema = 'Aberto'")
        return [row['numero_solicitacao'] for row in cur.fetchall()]


def marcar_como_respondidas(numeros_solicitacao):
    if not numeros_solicitacao:
        return
    with _get_cursor() as cur:
        cur.execute(
            "UPDATE solicitacoes SET status_sistema = 'Respondido' WHERE numero_solicitacao = ANY(%s)",
            (numeros_solicitacao,)
        )


def marcar_como_abertas(numeros_solicitacao):
    if not numeros_solicitacao:
        return
    with _get_cursor() as cur:
        cur.execute(
            "UPDATE solicitacoes SET status_sistema = 'Aberto' WHERE numero_solicitacao = ANY(%s)",
            (numeros_solicitacao,)
        )


def inserir_novas_solicitacoes(numeros_solicitacao):
    if not numeros_solicitacao:
        return
    timestamp_atual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with _get_cursor() as cur:
        for numero in numeros_solicitacao:
            cur.execute(
                "INSERT INTO solicitacoes (numero_solicitacao, recebido_em) VALUES (%s, %s) ON CONFLICT (numero_solicitacao) DO NOTHING",
                (numero, timestamp_atual)
            )


def atualizar_detalhes_solicitacao(dados_solicitacao):
    with _get_cursor() as cur:
        cur.execute("""
        UPDATE solicitacoes
        SET titulo = %s, npj_direcionador = %s, prazo = %s,
            texto_dmi = %s, numero_processo = %s, polo = %s
        WHERE numero_solicitacao = %s
        """, (
            dados_solicitacao.get("titulo"),
            dados_solicitacao.get("npj_direcionador"),
            dados_solicitacao.get("prazo"),
            dados_solicitacao.get("texto_dmi"),
            dados_solicitacao.get("numero_processo"),
            dados_solicitacao.get("polo"),
            dados_solicitacao.get("numero_solicitacao"),
        ))


def obter_solicitacoes_pendentes():
    with _get_cursor() as cur:
        cur.execute("""
        SELECT numero_solicitacao FROM solicitacoes
        WHERE status_sistema = 'Aberto'
          AND (
               titulo IS NULL
            OR numero_processo IS NULL
            OR numero_processo = ''
            OR numero_processo = 'Dado ausente na API'
            OR numero_processo LIKE 'Consulta pendente%%'
            OR numero_processo LIKE 'Erro na API%%'
            OR polo = 'Erro na API'
            OR polo = 'Pendente'
          );
        """)
        return [row['numero_solicitacao'] for row in cur.fetchall()]


# --- Funções de Usuários ---

def criar_usuario(name, password, role):
    password_hash = generate_password_hash(password)
    try:
        with _get_cursor() as cur:
            cur.execute(
                "INSERT INTO usuarios (name, password_hash, role) VALUES (%s, %s, %s)",
                (name, password_hash, role)
            )
    except psycopg2.IntegrityError:
        print(f"Erro: Nome de usuário '{name}' já cadastrado.")


def obter_usuario_por_nome(name):
    with _get_cursor() as cur:
        cur.execute("SELECT * FROM usuarios WHERE name = %s", (name,))
        row = cur.fetchone()
    if row:
        return User(row['id'], row['name'], row['password_hash'], row['role'])
    return None


def obter_todos_usuarios():
    with _get_cursor() as cur:
        cur.execute("SELECT * FROM usuarios ORDER BY name ASC")
        return cur.fetchall()


def obter_usuario_por_id(user_id):
    with _get_cursor() as cur:
        cur.execute("SELECT * FROM usuarios WHERE id = %s", (user_id,))
        return cur.fetchone()


def atualizar_usuario(user_id, name, role, new_password=None):
    with _get_cursor() as cur:
        if new_password:
            password_hash = generate_password_hash(new_password)
            cur.execute(
                "UPDATE usuarios SET name = %s, role = %s, password_hash = %s WHERE id = %s",
                (name, role, password_hash, user_id)
            )
        else:
            cur.execute(
                "UPDATE usuarios SET name = %s, role = %s WHERE id = %s",
                (name, role, user_id)
            )


def deletar_usuario(user_id):
    with _get_cursor() as cur:
        cur.execute("DELETE FROM usuarios WHERE id = %s", (user_id,))


# --- Funções Legal One ---

def obter_mapa_usuarios_id():
    with _get_cursor() as cur:
        cur.execute("SELECT external_id, name FROM legal_one_users")
        return {row['name']: row['external_id'] for row in cur.fetchall()}


def obter_usuarios_legal_one():
    with _get_cursor() as cur:
        cur.execute("SELECT name FROM legal_one_users ORDER BY name ASC")
        return cur.fetchall()


# --- Funções de Edição (usadas pelo Dashboard) ---

def atualizar_campos_edicao(num_solicitacao, responsavel, status, setor, data_agendamento):
    with _get_cursor() as cur:
        cur.execute("""
        UPDATE solicitacoes
        SET responsavel = %s, status = %s, setor = %s, data_agendamento = %s
        WHERE numero_solicitacao = %s
        """, (responsavel, status, setor, data_agendamento, num_solicitacao))


def atualizar_anotacao(num_solicitacao, anotacao):
    with _get_cursor() as cur:
        cur.execute(
            "UPDATE solicitacoes SET anotacao = %s WHERE numero_solicitacao = %s",
            (anotacao, num_solicitacao)
        )


# --- Funções novas (absorvem SQL inline do server.py) ---

def obter_solicitacoes_por_status(status, responsavel=None, busca=None):
    with _get_cursor() as cur:
        query = "SELECT * FROM solicitacoes WHERE status_sistema = %s"
        params = [status]

        if responsavel:
            query += " AND responsavel = %s"
            params.append(responsavel)

        if busca:
            query += " AND (numero_solicitacao ILIKE %s OR numero_processo ILIKE %s OR titulo ILIKE %s)"
            like = f"%{busca}%"
            params.extend([like, like, like])

        if status == 'Respondido':
            query += " ORDER BY id DESC"

        cur.execute(query, params)
        return cur.fetchall()


def obter_solicitacao_por_numero(numero):
    with _get_cursor() as cur:
        cur.execute("SELECT * FROM solicitacoes WHERE numero_solicitacao = %s", (numero,))
        return cur.fetchone()


def obter_recebimentos_por_periodo(inicio, fim):
    with _get_cursor() as cur:
        cur.execute(
            "SELECT recebido_em FROM solicitacoes WHERE recebido_em IS NOT NULL AND LEFT(recebido_em, 10) BETWEEN %s AND %s",
            (inicio, fim)
        )
        return cur.fetchall()
