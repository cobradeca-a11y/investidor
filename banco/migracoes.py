"""
banco/migracoes.py
Migrações idempotentes para bancos vivos do FIIA.

Objetivo:
- manter compatibilidade com fiia.db já criado antes das implementações P2/P3;
- evitar ALTER TABLE manual;
- permitir que python main.py --setup sincronize banco antigo com schema.sql atual.
"""
from __future__ import annotations

import sqlite3
from typing import Iterable


COLUNAS_P2_P3: dict[str, list[tuple[str, str]]] = {
    "indicadores": [
        ("preco_timestamp", "TEXT"),
        ("preco_fonte", "TEXT"),
        ("preco_moeda", "TEXT"),
    ],
    "dividendos": [
        ("data_base", "TEXT"),
        ("data_com", "TEXT"),
        ("protocolo", "TEXT"),
        ("url_documento", "TEXT"),
    ],
    "decisoes": [
        ("risco", "TEXT"),
        ("score_final", "REAL"),
        ("payload_json", "TEXT"),
        ("preco_teto", "REAL"),
    ],
}


def _tabela_existe(conn: sqlite3.Connection, tabela: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (tabela,),
    ).fetchone()
    return bool(row)


def _colunas_existentes(conn: sqlite3.Connection, tabela: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({tabela})").fetchall()
    return {str(row[1]) for row in rows}


def _adicionar_colunas(conn: sqlite3.Connection, tabela: str, colunas: Iterable[tuple[str, str]]) -> list[str]:
    if not _tabela_existe(conn, tabela):
        return []

    existentes = _colunas_existentes(conn, tabela)
    adicionadas: list[str] = []

    for nome, definicao in colunas:
        if nome not in existentes:
            conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {definicao}")
            adicionadas.append(f"{tabela}.{nome}")
            existentes.add(nome)

    return adicionadas


def aplicar_migracoes_p2_p3(conn: sqlite3.Connection) -> dict[str, object]:
    """Aplica migrações P2/P3 em conexão já aberta."""
    adicionadas: list[str] = []

    for tabela, colunas in COLUNAS_P2_P3.items():
        adicionadas.extend(_adicionar_colunas(conn, tabela, colunas))

    return {
        "migracao": "P2_P3_SCHEMA_VIVO",
        "colunas_adicionadas": adicionadas,
        "total_adicionadas": len(adicionadas),
    }
