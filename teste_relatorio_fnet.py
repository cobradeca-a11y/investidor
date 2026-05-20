"""
teste_relatorio_fnet.py

Regressao para compatibilidade do relatorio FNET com sqlite3.Row.
"""
from __future__ import annotations

import sqlite3

from coleta.relatorio_fnet import _valor_row


def test_valor_row_aceita_sqlite_row():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE fiis (ticker TEXT, nome TEXT)")
    conn.execute("INSERT INTO fiis VALUES ('HGLG11', 'CSHG LOGISTICA')")

    row = conn.execute("SELECT nome FROM fiis WHERE ticker = ?", ("HGLG11",)).fetchone()

    assert _valor_row(row, "nome") == "CSHG LOGISTICA"
    assert _valor_row(row, "ausente", "fallback") == "fallback"


def test_valor_row_aceita_dict_e_none():
    assert _valor_row({"nome": "FUNDO"}, "nome") == "FUNDO"
    assert _valor_row(None, "nome", "fallback") == "fallback"
