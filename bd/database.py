import os
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager

# Fuso de Brasilia para carimbar recebido_em corretamente, independente do
# fuso do servidor (o container roda em UTC). Usa zoneinfo quando disponivel;
# caso contrario, cai para UTC-3 fixo (Brasil nao observa horario de verao).
try:
    from zoneinfo import ZoneInfo
    TZ_BR = ZoneInfo("America/Sao_Paulo")
except Exception:
    TZ_BR = timezone(timedelta(hours=-3))
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
            status_sistema TEXT DEFAULT 'Aberto' NOT NULL,
            data_portal TEXT,
            status_portal TEXT,
            tem_anotacao_portal TEXT,
            fantasma BOOLEAN NOT NULL DEFAULT FALSE
        );
        """)
        # Colunas adicionadas depois (idempotente) para bancos ja existentes.
        cur.execute("ALTER TABLE solicitacoes ADD COLUMN IF NOT EXISTS data_portal TEXT;")
        cur.execute("ALTER TABLE solicitacoes ADD COLUMN IF NOT EXISTS status_portal TEXT;")
        cur.execute("ALTER TABLE solicitacoes ADD COLUMN IF NOT EXISTS tem_anotacao_portal TEXT;")
        # Fantasma: solicitacoes que aparecem na grade do portal mas cujo detalhe
        # nunca abre ("Nenhum registro encontrado"). Marcadas aqui (banco), setavel
        # pela UI/FLOW; descartadas do fluxo operacional.
        cur.execute("ALTER TABLE solicitacoes ADD COLUMN IF NOT EXISTS fantasma BOOLEAN NOT NULL DEFAULT FALSE;")
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
        # cookies_json guarda os cookies CIFRADOS (Fernet): quem cifra e decifra
        # é o server.py, e o banco nunca vê a sessão do BB em claro.
        cur.execute("""
        CREATE TABLE IF NOT EXISTS sessao_manual_bb (
            id SERIAL PRIMARY KEY,
            cookies_json TEXT NOT NULL,
            user_agent TEXT,
            criado_por TEXT,
            criado_em TEXT NOT NULL,
            expira_em TEXT NOT NULL,
            invalidada_em TEXT,
            motivo TEXT
        );
        """)


# --- Solicitações fantasma (descartadas) ---
# Alguns números aparecem na grade "Visão Advogado" que o Robô 1 lê, mas a busca
# pelo número no portal retorna "Nenhum registro encontrado" (o detalhe nunca abre).
# Sem tratamento, o sync as reabre a cada ciclo e o Robô 2 falha nelas eternamente.
# A marca vive no BANCO (coluna booleana `fantasma`), não no código: assim pode ser
# setada pela UI/FLOW. Uma solicitação com fantasma=TRUE é descartada — nunca reaberta
# pelo sync, nunca cobrada de detalhe, e some de todas as telas/consultas operacionais.

def marcar_como_fantasma(numeros_solicitacao, valor=True):
    """Liga/desliga o flag `fantasma` de uma ou mais solicitações."""
    numeros = list(numeros_solicitacao)
    if not numeros:
        return
    with _get_cursor() as cur:
        cur.execute(
            "UPDATE solicitacoes SET fantasma = %s WHERE numero_solicitacao = ANY(%s)",
            (bool(valor), numeros)
        )


def obter_solicitacoes_fantasma():
    """Números atualmente marcados como fantasma (para conferência/admin)."""
    with _get_cursor() as cur:
        cur.execute(
            "SELECT numero_solicitacao FROM solicitacoes WHERE fantasma = TRUE ORDER BY numero_solicitacao"
        )
        return [row['numero_solicitacao'] for row in cur.fetchall()]


# --- Funções de Sincronização de Status (usadas pelo RPA) ---

def obter_solicitacoes_abertas_db():
    with _get_cursor() as cur:
        cur.execute(
            "SELECT numero_solicitacao FROM solicitacoes WHERE status_sistema = 'Aberto' AND fantasma = FALSE"
        )
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
            "UPDATE solicitacoes SET status_sistema = 'Aberto' WHERE numero_solicitacao = ANY(%s) AND fantasma = FALSE",
            (numeros_solicitacao,)
        )


def inserir_novas_solicitacoes(numeros_solicitacao):
    if not numeros_solicitacao:
        return
    timestamp_atual = datetime.now(TZ_BR).strftime('%Y-%m-%d %H:%M:%S')
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
            texto_dmi = %s, numero_processo = %s, polo = %s,
            data_portal = COALESCE(%s, data_portal)
        WHERE numero_solicitacao = %s
        """, (
            dados_solicitacao.get("titulo"),
            dados_solicitacao.get("npj_direcionador"),
            dados_solicitacao.get("prazo"),
            dados_solicitacao.get("texto_dmi"),
            dados_solicitacao.get("numero_processo"),
            dados_solicitacao.get("polo"),
            dados_solicitacao.get("data_portal") or None,
            dados_solicitacao.get("numero_solicitacao"),
        ))


def obter_solicitacoes_vencem_hoje():
    """Numeros das solicitacoes ABERTAS cujo prazo (DD/MM/AAAA) e hoje OU atrasadas (fuso de Brasilia).

    Compara sem TO_DATE: filtra apenas prazos no formato DD/MM/YYYY e reformata para
    YYYY-MM-DD (substr, que nunca lanca erro) para comparar como texto ISO. Assim um
    prazo malformado e simplesmente ignorado, em vez de derrubar a consulta inteira (500).
    """
    hoje_iso = datetime.now(TZ_BR).strftime('%Y-%m-%d')
    with _get_cursor() as cur:
        cur.execute("""
            SELECT numero_solicitacao FROM solicitacoes
            WHERE status_sistema = 'Aberto'
              AND fantasma = FALSE
              AND prazo ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$'
              AND (substr(prazo, 7, 4) || '-' || substr(prazo, 4, 2) || '-' || substr(prazo, 1, 2)) <= %s
        """, (hoje_iso,))
        return [row['numero_solicitacao'] for row in cur.fetchall()]


def obter_solicitacoes_atrasadas():
    """Numeros das solicitacoes ABERTAS cujo prazo (DD/MM/AAAA) JA PASSOU (atrasadas), fuso de Brasilia.

    Igual a obter_solicitacoes_vencem_hoje, mas com '<' (estritamente antes de hoje):
    exclui as que vencem HOJE. Usado para rodar a verificacao de anotacao do portal
    apenas nas atrasadas.
    """
    hoje_iso = datetime.now(TZ_BR).strftime('%Y-%m-%d')
    with _get_cursor() as cur:
        cur.execute("""
            SELECT numero_solicitacao FROM solicitacoes
            WHERE status_sistema = 'Aberto'
              AND fantasma = FALSE
              AND prazo ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$'
              AND (substr(prazo, 7, 4) || '-' || substr(prazo, 4, 2) || '-' || substr(prazo, 1, 2)) < %s
        """, (hoje_iso,))
        return [row['numero_solicitacao'] for row in cur.fetchall()]


def atualizar_status_portal(numero_solicitacao, status_portal, tem_anotacao_portal=None):
    """Atualiza o status do portal (ex.: 'Em Elaboracao') de uma solicitacao.

    tem_anotacao_portal: 'Sim'/'Não' quando verificado; None nao altera a coluna
    (preserva o ultimo valor conhecido).
    """
    with _get_cursor() as cur:
        if tem_anotacao_portal is None:
            cur.execute(
                "UPDATE solicitacoes SET status_portal = %s WHERE numero_solicitacao = %s",
                (status_portal, numero_solicitacao)
            )
        else:
            cur.execute(
                "UPDATE solicitacoes SET status_portal = %s, tem_anotacao_portal = %s WHERE numero_solicitacao = %s",
                (status_portal, tem_anotacao_portal, numero_solicitacao)
            )


SESSAO_MANUAL_VALIDADE_HORAS = 2


def guardar_sessao_manual(cookies_json, user_agent, criado_por):
    agora = datetime.now(TZ_BR)
    expira = agora + timedelta(hours=SESSAO_MANUAL_VALIDADE_HORAS)
    with _get_cursor() as cur:
        cur.execute("DELETE FROM sessao_manual_bb")
        cur.execute("""
            INSERT INTO sessao_manual_bb (cookies_json, user_agent, criado_por, criado_em, expira_em)
            VALUES (%s, %s, %s, %s, %s)
        """, (cookies_json, user_agent, criado_por,
              agora.isoformat(), expira.isoformat()))


def obter_sessao_manual_vigente():
    agora_iso = datetime.now(TZ_BR).isoformat()
    with _get_cursor() as cur:
        cur.execute("""
            SELECT id, cookies_json, user_agent, criado_por
            FROM sessao_manual_bb
            WHERE invalidada_em IS NULL AND expira_em > %s
            ORDER BY id DESC LIMIT 1
        """, (agora_iso,))
        return cur.fetchone()


def estado_sessao_manual():
    with _get_cursor() as cur:
        cur.execute("""
            SELECT criado_por, criado_em, expira_em, invalidada_em, motivo
            FROM sessao_manual_bb
            ORDER BY id DESC LIMIT 1
        """)
        row = cur.fetchone()
    if not row:
        return {"ativa": False, "validade_horas": SESSAO_MANUAL_VALIDADE_HORAS}
    agora_iso = datetime.now(TZ_BR).isoformat()
    ativa = row['invalidada_em'] is None and row['expira_em'] > agora_iso
    return {
        "ativa": ativa,
        "validade_horas": SESSAO_MANUAL_VALIDADE_HORAS,
        "criado_por": row['criado_por'],
        "criado_em": row['criado_em'],
        "expira_em": row['expira_em'],
        "invalidada_em": row['invalidada_em'],
        "motivo": row['motivo'],
    }


def invalidar_sessao_manual(motivo, sessao_id=None):
    """Tira a sessão colada de uso. Com `sessao_id`, só aquela: o robô que
    testou uma sessão antiga não pode derrubar a que o operador acabou de
    colar (guardar_sessao_manual troca a linha, e o id muda)."""
    agora_iso = datetime.now(TZ_BR).isoformat()
    with _get_cursor() as cur:
        if sessao_id is not None:
            cur.execute("""
                UPDATE sessao_manual_bb SET invalidada_em = %s, motivo = %s
                WHERE id = %s AND invalidada_em IS NULL
            """, (agora_iso, motivo, sessao_id))
        else:
            cur.execute("""
                UPDATE sessao_manual_bb SET invalidada_em = %s, motivo = %s
                WHERE invalidada_em IS NULL
            """, (agora_iso, motivo))


def descartar_sessao_manual():
    with _get_cursor() as cur:
        cur.execute("DELETE FROM sessao_manual_bb")


def obter_solicitacoes_pendentes():
    with _get_cursor() as cur:
        cur.execute("""
        SELECT numero_solicitacao FROM solicitacoes
        WHERE status_sistema = 'Aberto'
          AND fantasma = FALSE
          AND (
               titulo IS NULL
            OR numero_processo IS NULL
            OR numero_processo = ''
            OR numero_processo = 'Dado ausente na API'
            OR numero_processo LIKE 'Consulta pendente%%'
            OR numero_processo LIKE 'Erro na API%%'
            OR polo = 'Erro na API'
            OR polo = 'Pendente'
            OR numero_processo = 'Acesso não autorizado'
            OR titulo = 'Acesso não autorizado'
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
