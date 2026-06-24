"""
Script de migração one-time: copia dados do SQLite local para o PostgreSQL.

Uso:
  1. Certifique-se de que o PostgreSQL está rodando (docker-compose up db)
  2. Defina DATABASE_URL no .env ou como variável de ambiente
  3. Execute: python scripts/migrar_sqlite_postgres.py
"""

import sqlite3
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))

import psycopg2

SQLITE_SOLICITACOES = os.path.join(project_root, 'bd', 'solicitacoes.db')
SQLITE_LEGAL_ONE = os.path.join(project_root, 'bd', 'database.db')
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://onerequest:senha_segura@localhost:5432/onerequest')


def migrar():
    print(f"Conectando ao PostgreSQL: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")
    pg_conn = psycopg2.connect(DATABASE_URL)
    pg_cur = pg_conn.cursor()

    pg_cur.execute("""
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
    pg_cur.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'user' NOT NULL
    );
    """)
    pg_cur.execute("""
    CREATE TABLE IF NOT EXISTS legal_one_users (
        id SERIAL PRIMARY KEY,
        name TEXT,
        external_id TEXT
    );
    """)
    pg_conn.commit()

    if os.path.exists(SQLITE_SOLICITACOES):
        print(f"\nMigrando solicitações de {SQLITE_SOLICITACOES}...")
        sq_conn = sqlite3.connect(SQLITE_SOLICITACOES)
        sq_conn.row_factory = sqlite3.Row

        rows = sq_conn.execute("SELECT * FROM solicitacoes").fetchall()
        count = 0
        for row in rows:
            r = dict(row)
            pg_cur.execute("""
            INSERT INTO solicitacoes (
                numero_solicitacao, titulo, npj_direcionador, prazo,
                texto_dmi, numero_processo, polo, recebido_em,
                responsavel, anotacao, status, setor,
                data_agendamento, status_sistema
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (numero_solicitacao) DO NOTHING
            """, (
                r.get('numero_solicitacao'), r.get('titulo'), r.get('npj_direcionador'), r.get('prazo'),
                r.get('texto_dmi'), r.get('numero_processo'), r.get('polo'), r.get('recebido_em'),
                r.get('responsavel', 'N/A'), r.get('anotacao', ''), r.get('status', 'Não'),
                r.get('setor', 'N/A'), r.get('data_agendamento', ''), r.get('status_sistema', 'Aberto'),
            ))
            count += 1
        pg_conn.commit()
        print(f"  {count} solicitações processadas.")

        usuarios = sq_conn.execute("SELECT * FROM usuarios").fetchall()
        count_u = 0
        for u in usuarios:
            u = dict(u)
            pg_cur.execute("""
            INSERT INTO usuarios (name, password_hash, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (name) DO NOTHING
            """, (u['name'], u['password_hash'], u['role']))
            count_u += 1
        pg_conn.commit()
        print(f"  {count_u} usuários processados.")
        sq_conn.close()
    else:
        print(f"Arquivo {SQLITE_SOLICITACOES} não encontrado. Pulando migração de solicitações.")

    if os.path.exists(SQLITE_LEGAL_ONE):
        print(f"\nMigrando legal_one_users de {SQLITE_LEGAL_ONE}...")
        sq_conn2 = sqlite3.connect(SQLITE_LEGAL_ONE)
        sq_conn2.row_factory = sqlite3.Row

        try:
            users_lo = sq_conn2.execute("SELECT name, external_id FROM legal_one_users").fetchall()
            count_lo = 0
            for u in users_lo:
                u = dict(u)
                pg_cur.execute("""
                INSERT INTO legal_one_users (name, external_id)
                VALUES (%s, %s)
                """, (u['name'], u.get('external_id')))
                count_lo += 1
            pg_conn.commit()
            print(f"  {count_lo} usuários Legal One processados.")
        except sqlite3.OperationalError as e:
            print(f"  Aviso: Não foi possível migrar legal_one_users: {e}")
        finally:
            sq_conn2.close()
    else:
        print(f"Arquivo {SQLITE_LEGAL_ONE} não encontrado. Pulando migração Legal One.")

    pg_cur.execute("SELECT setval('solicitacoes_id_seq', COALESCE((SELECT MAX(id) FROM solicitacoes), 1))")
    pg_cur.execute("SELECT setval('usuarios_id_seq', COALESCE((SELECT MAX(id) FROM usuarios), 1))")
    pg_cur.execute("SELECT setval('legal_one_users_id_seq', COALESCE((SELECT MAX(id) FROM legal_one_users), 1))")
    pg_conn.commit()

    pg_cur.close()
    pg_conn.close()
    print("\nMigração concluída com sucesso!")


if __name__ == '__main__':
    migrar()
