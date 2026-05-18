"""
teste_proibicao_sqlite.py
Testa se a execução em modo contexto é 100% isolada do banco de dados e APIs externas.
"""
import pytest
import requests
import sqlite3
import yfinance as yf

from banco import db
from coleta.contexto_ativo import obter_contexto_ativo
from decisao import motor_decisao_cvm_first, decisao_com_confianca
from sistema import observabilidade


class IsolamentoZeroDB:
    """
    Context manager que intercepta e proíbe agressivamente qualquer acesso
    ao SQLite, à rede (requests, yfinance) e escrita em disco (logs).
    """
    def __enter__(self):
        def db_error_mock(*args, **kwargs):
            raise AssertionError("PROIBIDO: Motor acessou o SQLite em modo contexto!")

        def requests_error_mock(*args, **kwargs):
            raise AssertionError("PROIBIDO: Motor efetuou requisição HTTP em modo contexto!")

        def yf_error_mock(*args, **kwargs):
            raise AssertionError("PROIBIDO: Motor acessou APIs do yfinance em modo contexto!")

        self.orig_buscar_um = db.buscar_um
        self.orig_buscar_todos = db.buscar_todos
        self.orig_executar = db.executar
        self.orig_upsert = getattr(db, "upsert", None)
        self.orig_inserir = getattr(db, "inserir", None)
        self.orig_transacao = getattr(db, "transacao", None)
        self.orig_conectar = getattr(db, "conectar", None)
        self.orig_sqlite_connect = sqlite3.connect
        
        self.orig_requests_get = requests.get
        self.orig_requests_post = requests.post
        self.orig_yf_ticker = yf.Ticker
        
        self.orig_registrar_evento = observabilidade.registrar_evento
        self.orig_registrar_erro = observabilidade.registrar_erro

        db.buscar_um = db_error_mock
        db.buscar_todos = db_error_mock
        db.executar = db_error_mock
        if self.orig_upsert is not None:
            db.upsert = db_error_mock
        if self.orig_inserir is not None:
            db.inserir = db_error_mock
        if self.orig_transacao is not None:
            db.transacao = db_error_mock
        if self.orig_conectar is not None:
            db.conectar = db_error_mock

        sqlite3.connect = db_error_mock

        requests.get = requests_error_mock
        requests.post = requests_error_mock
        yf.Ticker = yf_error_mock

        # Mock de observabilidade para memória pura (sem efeito colateral em disco)
        observabilidade.registrar_evento = lambda *args, **kwargs: None
        observabilidade.registrar_erro = lambda *args, **kwargs: None

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        db.buscar_um = self.orig_buscar_um
        db.buscar_todos = self.orig_buscar_todos
        db.executar = self.orig_executar
        if self.orig_upsert is not None:
            db.upsert = self.orig_upsert
        if self.orig_inserir is not None:
            db.inserir = self.orig_inserir
        if self.orig_transacao is not None:
            db.transacao = self.orig_transacao
        if self.orig_conectar is not None:
            db.conectar = self.orig_conectar

        sqlite3.connect = self.orig_sqlite_connect

        requests.get = self.orig_requests_get
        requests.post = self.orig_requests_post
        yf.Ticker = self.orig_yf_ticker

        observabilidade.registrar_evento = self.orig_registrar_evento
        observabilidade.registrar_erro = self.orig_registrar_erro


def test_proibicao_sqlite_no_decisao():
    ticker = "HGLG11"
    
    # 1. Resolve o contexto ANTES do monkeypatching de isolamento
    contexto = obter_contexto_ativo(ticker)
    
    assert contexto is not None
    assert contexto["ticker"] == "HGLG11"
    assert contexto["preco"] is not None
    assert contexto["vpa"] is not None
    
    with IsolamentoZeroDB():
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
        assert len(veredito["trilha_gates"]) > 0


def test_proibicao_sqlite_contexto_incompleto():
    ticker = "HGLG11"
    
    contexto_incompleto = {
        "ticker": "HGLG11",
        "preco": 160.0
    }

    def db_error_mock(*args, **kwargs):
        raise AssertionError("PROIBIDO: Acessou o SQLite mesmo com contexto incompleto!")

    orig_buscar_um = db.buscar_um
    db.buscar_um = db_error_mock

    try:
        veredito = motor_decisao_cvm_first.decidir(
            ticker,
            contexto=contexto_incompleto
        )
        assert veredito["decisao"] == "BLOQUEADO_CONTEXTO_INCOMPLETO"
        assert "Campos ausentes" in veredito["motivo"]
    finally:
        db.buscar_um = orig_buscar_um


def test_proibicao_sqlite_decisao_com_confianca():
    """
    Assegura que o ponto de entrada real decisao_com_confianca.decidir
    roda em modo 100% in-memory sem acessar SQLite, APIs de rede ou logs de disco.
    """
    ticker = "HGLG11"
    contexto = obter_contexto_ativo(ticker)
    
    assert contexto is not None

    with IsolamentoZeroDB():
        veredito = decisao_com_confianca.decidir(
            ticker,
            score_ia=8.5,
            riscos_ia=["Exposição logístico AAA"],
            tom_gestor="neutro",
            ia_status="OK",
            contexto=contexto
        )

        assert veredito is not None
        assert "decisao" in veredito
        assert veredito["ticker"] == ticker
        # Assegura que gerou a confiança de dados consolidados sem tocar no banco
        assert veredito["score_confianca_dados_consolidado"] > 0
        assert veredito["nivel_uso_dados_consolidado"] is not None

