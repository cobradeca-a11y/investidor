"""
banco/db.py
Conexão com o banco SQLite e helpers de acesso.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from banco.migracoes import aplicar_migracoes_p2_p3

# Caminho do banco — sempre na raiz do projeto
_RAIZ = Path(__file__).parent.parent
DB_PATH = _RAIZ / "fiia.db"
SCHEMA_PATH = _RAIZ / "schema.sql"


def conectar() -> sqlite3.Connection:
    """Retorna conexão com o banco com foreign keys ativas."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def transacao() -> Iterator[sqlite3.Connection]:
    """
    Abre uma transação explícita para operações compostas.

    Use quando duas ou mais escritas precisam ser atômicas.
    Em caso de erro, executa rollback e relança a exceção.
    """
    conn = conectar()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def inicializar() -> None:
    """
    Cria as tabelas se ainda não existirem e aplica migrações idempotentes.

    Objetivo:
    - banco novo nasce sincronizado com schema.sql;
    - banco antigo recebe colunas P2/P3 automaticamente.
    """
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = conectar()
    try:
        conn.executescript(schema)

        migracao = aplicar_migracoes_p2_p3(conn)

        conn.commit()
    finally:
        conn.close()

    print(f"[db] Banco inicializado em: {DB_PATH}")
    if migracao["total_adicionadas"]:
        print(f"[db] Migração P2/P3 aplicada: {migracao['colunas_adicionadas']}")
    else:
        print("[db] Banco já estava sincronizado com P2/P3.")


def inserir(tabela: str, dados: dict[str, Any]) -> int:
    """
    Insere um registro e retorna o id gerado.

    Atenção: usa INSERT OR IGNORE. Em caso de duplicidade ignorada,
    o SQLite pode retornar lastrowid sem criar novo registro.
    """
    colunas = ", ".join(dados.keys())
    placeholders = ", ".join("?" * len(dados))
    sql = f"INSERT OR IGNORE INTO {tabela} ({colunas}) VALUES ({placeholders})"
    conn = conectar()
    try:
        cursor = conn.execute(sql, list(dados.values()))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def upsert(tabela: str, dados: dict[str, Any]) -> None:
    """Insere ou substitui um registro."""
    colunas = ", ".join(dados.keys())
    placeholders = ", ".join("?" * len(dados))
    sql = f"INSERT OR REPLACE INTO {tabela} ({colunas}) VALUES ({placeholders})"
    conn = conectar()
    try:
        conn.execute(sql, list(dados.values()))
        conn.commit()
    finally:
        conn.close()


def buscar_um(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    """Retorna um único registro ou None."""
    conn = conectar()
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def buscar_todos(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """Retorna lista de registros."""
    conn = conectar()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def executar(sql: str, params: tuple = ()) -> None:
    """Executa SQL sem retorno (UPDATE, DELETE)."""
    conn = conectar()
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def get_by_ticker(tabela: str, ticker: str) -> dict | None:
    """Helper para buscar dados de um FII pelo ticker."""
    sql = f"SELECT * FROM {tabela} WHERE ticker = ?"
    row = buscar_um(sql, (ticker,))
    return dict(row) if row else None
