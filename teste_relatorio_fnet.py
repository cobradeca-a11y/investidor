"""
teste_relatorio_fnet.py

Regressao para compatibilidade do relatorio FNET com sqlite3.Row.
"""
from __future__ import annotations

import sqlite3

from coleta.relatorio_fnet import (
    _documento_local_prioritario,
    _motivo_resposta_nao_pdf,
    _params_fnet,
    _parece_pdf,
    _prioridade_doc_local,
    _valor_row,
)


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


def test_params_fnet_monta_tipo_documental():
    params = _params_fnet("11222333000144", "41")

    assert params["tipoFundo"] == "1"
    assert params["idCategoriaDocumento"] == "6"
    assert params["idTipoDocumento"] == "41"
    assert params["cnpj"] == "11222333000144"


def test_prioridade_doc_local_mensal_antes_de_trimestral_e_anual():
    mensal = {"tipo_documento": "INFORME_MENSAL", "data_referencia": "2026-01-01"}
    trimestral = {"tipo_documento": "INFORME_TRIMESTRAL", "data_referencia": "2026-04-01"}
    anual = {"tipo_documento": "INFORME_ANUAL", "data_referencia": "2025-12-31"}

    assert _prioridade_doc_local(mensal) < _prioridade_doc_local(trimestral)
    assert _prioridade_doc_local(trimestral) < _prioridade_doc_local(anual)


def test_documento_local_prioritario_ignora_sem_doc_id(monkeypatch):
    docs = [
        {"tipo_documento": "INFORME_ANUAL", "protocolo": "3"},
        {"tipo_documento": "INFORME_MENSAL"},
        {"tipo_documento": "INFORME_TRIMESTRAL", "url_documento": "https://x?id=2"},
    ]

    monkeypatch.setattr("coleta.relatorio_fnet.cvm_fnet_documentos.listar_por_cnpj", lambda cnpj, limite=50: docs)

    assert _documento_local_prioritario("00.000.000/0001-00")["url_documento"] == "https://x?id=2"
