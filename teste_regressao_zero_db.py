import copy
import sqlite3

import requests
import yfinance as yf

from banco import db
from decisao import decisao_com_confianca, motor_decisao, motor_decisao_cvm_first
from decisao.objeto_decisao import CONTRATO_DECISAO_CAMPOS
from sistema import observabilidade


def contexto_deterministico() -> dict:
    return {
        "ticker": "TEST11",
        "nome_fundo": "FIIA Teste Deterministico",
        "tipo": "PAPEL",
        "segmento": "PAPEL",
        "preco": 95.0,
        "preco_timestamp": "2026-05-18T12:00:00+00:00",
        "preco_fonte": "fixture",
        "preco_moeda": "BRL",
        "vpa": 100.0,
        "pvp": 0.95,
        "patrimonio_liquido": 500_000_000.0,
        "patrimonio_fonte": "CVM_INF_MENSAL",
        "competencia_patrimonial": "2026-04",
        "liquidez_diaria": 2_500_000.0,
        "ultimo_dividendo": 1.10,
        "dy_12m": 0.155,
        "dy_3m": 0.038,
        "dy_6m": 0.077,
        "dy_recorrente": 0.150,
        "recorrencia_dividendos_pct": 1.0,
        "meses_historico": 36,
        "quedas_consecutivas": 0,
        "vacancia_fisica": None,
        "qtd_ativos": 50,
        "score_confianca": 95,
        "nivel_uso_dados": "CONFIAVEL",
        "campos_vencidos": [],
        "cdi_atual": 12.0,
        "selic_atual": 12.25,
        "ipca_atual": 4.0,
        "premio_cdi": 3.0,
        "semaforo_macro": {
            "cor": "VERDE",
            "motivo": "Fixture macro favoravel",
            "teto_decisao": "COMPRAR",
            "tendencia": "ESTAVEL",
        },
        "teto_macro": "COMPRAR",
        "permitir_decisao": True,
        "contexto_versao": "asset-context-fixture",
        "eventos_fnet": {
            "ticker": "TEST11",
            "nivel_risco_documental": "BAIXO",
            "documentos_relevantes": [],
            "eventos_relevantes": [],
            "total_eventos": 0,
            "score_documental_fnet": 100,
            "penalizacao_score": 0,
            "bonificacao_score": 0,
            "sinalizacao_fnet": "NEUTRO",
        },
    }


class BloqueioIO:
    def __enter__(self):
        def erro(*args, **kwargs):
            raise AssertionError("PROIBIDO: acesso a IO em regressao Zero DB")

        self.originais = {
            "buscar_um": db.buscar_um,
            "buscar_todos": db.buscar_todos,
            "executar": db.executar,
            "upsert": getattr(db, "upsert", None),
            "inserir": getattr(db, "inserir", None),
            "transacao": getattr(db, "transacao", None),
            "conectar": getattr(db, "conectar", None),
            "sqlite_connect": sqlite3.connect,
            "requests_get": requests.get,
            "requests_post": requests.post,
            "yf_ticker": yf.Ticker,
            "registrar_evento": observabilidade.registrar_evento,
            "registrar_erro": observabilidade.registrar_erro,
        }

        db.buscar_um = erro
        db.buscar_todos = erro
        db.executar = erro
        if self.originais["upsert"] is not None:
            db.upsert = erro
        if self.originais["inserir"] is not None:
            db.inserir = erro
        if self.originais["transacao"] is not None:
            db.transacao = erro
        if self.originais["conectar"] is not None:
            db.conectar = erro
        sqlite3.connect = erro
        requests.get = erro
        requests.post = erro
        yf.Ticker = erro
        observabilidade.registrar_evento = lambda *args, **kwargs: None
        observabilidade.registrar_erro = lambda *args, **kwargs: None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        db.buscar_um = self.originais["buscar_um"]
        db.buscar_todos = self.originais["buscar_todos"]
        db.executar = self.originais["executar"]
        if self.originais["upsert"] is not None:
            db.upsert = self.originais["upsert"]
        if self.originais["inserir"] is not None:
            db.inserir = self.originais["inserir"]
        if self.originais["transacao"] is not None:
            db.transacao = self.originais["transacao"]
        if self.originais["conectar"] is not None:
            db.conectar = self.originais["conectar"]
        sqlite3.connect = self.originais["sqlite_connect"]
        requests.get = self.originais["requests_get"]
        requests.post = self.originais["requests_post"]
        yf.Ticker = self.originais["yf_ticker"]
        observabilidade.registrar_evento = self.originais["registrar_evento"]
        observabilidade.registrar_erro = self.originais["registrar_erro"]


def _assert_contrato(payload: dict) -> None:
    for campo in CONTRATO_DECISAO_CAMPOS:
        assert campo in payload, f"Campo ausente: {campo}"
    assert payload["ticker"] == "TEST11"
    assert payload["contexto_versao"] == "asset-context-fixture"
    assert isinstance(payload["gates_detalhes"], dict)


def test_motor_base_zero_db_com_contexto_deterministico():
    contexto = contexto_deterministico()
    with BloqueioIO():
        veredito = motor_decisao.decidir(
            "TEST11",
            score_ia=8.5,
            riscos_ia=[],
            tom_gestor="neutro",
            ia_status="OK",
            contexto=copy.deepcopy(contexto),
        )

    assert veredito["ticker"] == "TEST11"
    assert veredito["trilha_gates"]
    assert veredito["gates_detalhes"]


def test_motor_cvm_first_zero_db_com_contexto_deterministico():
    contexto = contexto_deterministico()
    with BloqueioIO():
        veredito = motor_decisao_cvm_first.decidir(
            "TEST11",
            score_ia=8.5,
            riscos_ia=[],
            tom_gestor="neutro",
            ia_status="OK",
            contexto=copy.deepcopy(contexto),
        )

    _assert_contrato(veredito)
    assert "gate55_confianca_dados" in veredito


def test_decisao_com_confianca_zero_db_com_contexto_deterministico():
    contexto = contexto_deterministico()
    with BloqueioIO():
        veredito = decisao_com_confianca.decidir(
            "TEST11",
            score_ia=8.5,
            riscos_ia=[],
            tom_gestor="neutro",
            ia_status="OK",
            contexto=copy.deepcopy(contexto),
        )

    _assert_contrato(veredito)
    assert veredito["confianca_dados"]
