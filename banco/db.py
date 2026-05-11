"""
banco/db.py
Conexão com o banco SQLite e helpers de acesso.
"""
import sqlite3
from pathlib import Path
from typing import Any

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


def inicializar() -> None:
    """Cria as tabelas se ainda não existirem."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = conectar()
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()
    print(f"[db] Banco inicializado em: {DB_PATH}")


def inserir(tabela: str, dados: dict[str, Any]) -> int:
    """Insere um registro e retorna o id gerado."""
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
