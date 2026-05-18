"""
teste_proibicao_sqlite.py
Testa se a execução em modo contexto é 100% isolada do banco de dados e APIs externas.
"""
import pytest
import requests
import yfinance as yf

from banco import db
from coleta.contexto_ativo import obter_contexto_ativo
from decisao import motor_decisao_cvm_first


def test_proibicao_sqlite_no_decisao():
    ticker = "HGLG11"
    
    # 1. Resolve o contexto ANTES do monkeypatching de isolamento
    contexto = obter_contexto_ativo(ticker)
    
    assert contexto is not None
    assert contexto["ticker"] == "HGLG11"
    assert contexto["preco"] is not None
    assert contexto["vpa"] is not None
    
    # 2. Cria funções de erro para barrar acessos
    def db_error_mock(*args, **kwargs):
        raise AssertionError("PROIBIDO: Motor acessou o SQLite em modo contexto!")

    def requests_error_mock(*args, **kwargs):
        raise AssertionError("PROIBIDO: Motor efetuou requisição HTTP em modo contexto!")

    def yf_error_mock(*args, **kwargs):
        raise AssertionError("PROIBIDO: Motor acessou APIs do yfinance em modo contexto!")

    # Guarda referências originais
    orig_buscar_um = db.buscar_um
    orig_buscar_todos = db.buscar_todos
    orig_executar = db.executar
    orig_upsert = getattr(db, "upsert", None)

    orig_requests_get = requests.get
    orig_requests_post = requests.post
    orig_yf_ticker = yf.Ticker

    # Aplica o isolamento total
    db.buscar_um = db_error_mock
    db.buscar_todos = db_error_mock
    db.executar = db_error_mock
    if orig_upsert is not None:
        db.upsert = db_error_mock

    requests.get = requests_error_mock
    requests.post = requests_error_mock
    yf.Ticker = yf_error_mock

    try:
        # 3. Executa a decisão - deve passar de forma 100% in-memory
        veredito = motor_decisao_cvm_first.decidir(
            ticker,
            score_ia=8.5,
            riscos_ia=["Exposição a galpões logísticos padrão AAA"],
            tom_gestor="neutro",
            ia_status="OK",
            contexto=contexto
        )

        # 4. Assegura que retornou o veredito esperado sem tocar no banco
        assert veredito is not None
        assert "decisao" in veredito
        assert veredito["ticker"] == ticker
        # Trilha deve constar Gates avaliados
        assert len(veredito["trilha_gates"]) > 0

    finally:
        # Restaura as funções originais
        db.buscar_um = orig_buscar_um
        db.buscar_todos = orig_buscar_todos
        db.executar = orig_executar
        if orig_upsert is not None:
            db.upsert = orig_upsert

        requests.get = orig_requests_get
        requests.post = orig_requests_post
        yf.Ticker = orig_yf_ticker


def test_proibicao_sqlite_contexto_incompleto():
    ticker = "HGLG11"
    
    # Contexto faltante (incompleto)
    contexto_incompleto = {
        "ticker": "HGLG11",
        "preco": 160.0
    }

    # Bloqueia acessos para garantir que falha logo na validação, sem tocar no BD
    def db_error_mock(*args, **kwargs):
        raise AssertionError("PROIBIDO: Acessou o SQLite mesmo com contexto incompleto!")

    orig_buscar_um = db.buscar_um
    db.buscar_um = db_error_mock

    try:
        veredito = motor_decisao_cvm_first.decidir(
            ticker,
            contexto=contexto_incompleto
        )
        # Deve retornar o status de bloqueio correto
        assert veredito["decisao"] == "BLOQUEADO_CONTEXTO_INCOMPLETO"
        assert "Campos ausentes" in veredito["motivo"]
    finally:
        db.buscar_um = orig_buscar_um
