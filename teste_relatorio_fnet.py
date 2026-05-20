"""
teste_relatorio_fnet.py

Regressao para compatibilidade do relatorio FNET com sqlite3.Row.
"""
from __future__ import annotations

import sqlite3

from coleta.relatorio_fnet import _motivo_resposta_nao_pdf, _parece_pdf, _valor_row


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


def test_parece_pdf_valida_assinatura_antes_do_parser():
    assert _parece_pdf(b"%PDF-1.7\n" + (b"0" * 300), "")
    assert not _parece_pdf(b"<html>erro fnet</html>" + (b"0" * 300), "text/html")
    assert not _parece_pdf(b"{}", "application/json")
    assert not _parece_pdf(b"nao-pdf" + (b"0" * 300), "application/pdf")


def test_motivo_resposta_nao_pdf_classifica_html_json_e_curto():
    assert "html" in _motivo_resposta_nao_pdf(b"<html>erro</html>" + (b"0" * 300), "text/html")
    assert "json" in _motivo_resposta_nao_pdf(b'{"erro": true}' + (b"0" * 300), "application/json")
    assert "curta" in _motivo_resposta_nao_pdf(b"abc", "")
