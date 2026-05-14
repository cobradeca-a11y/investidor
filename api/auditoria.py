"""
api/auditoria.py

Endpoints de auditoria operacional do FIIA.

Objetivo:
- expor decisões recentes;
- expor taxa de acerto 90/365d;
- expor uso de CVM vs fallback patrimonial;
- expor Gate 5.5;
- expor confiança dos dados;
- detectar instabilidade de decisão por ticker.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from fastapi import APIRouter

from banco import db
from aprendizado.avaliador import taxa_acerto
from sistema import observabilidade

router = APIRouter(prefix="/api/auditoria", tags=["auditoria"])


def _json_para_dict(valor: Any) -> dict[str, Any]:
    if not valor:
        return {}
    if isinstance(valor, dict):
        return valor
    try:
        return json.loads(valor)
    except Exception:
        return {}


def _listar_decisoes(limite: int = 50) -> list[dict[str, Any]]:
    rows = db.buscar_todos(
        """
        SELECT * FROM decisoes
        ORDER BY data_decisao DESC, id DESC
        LIMIT ?
        """,
        (limite,),
    )
    return [dict(row) for row in rows]


@router.get("/decisoes")
def listar_decisoes(limite: int = 50) -> dict[str, Any]:
    """Lista decisões recentes com campos auditáveis principais."""
    try:
        decisoes = []
        for row in _listar_decisoes(limite):
            payload = _json_para_dict(row.get("payload_json"))
            gate55 = payload.get("gate55_confianca_dados", {}) or {}
            patrimonio = payload.get("patrimonio_resolvido", {}) or {}

            decisoes.append(
                {
                    "id": row.get("id"),
                    "ticker": row.get("ticker"),
                    "data_decisao": row.get("data_decisao"),
                    "decisao": row.get("decisao"),
                    "risco": row.get("risco"),
                    "confianca": row.get("confianca"),
                    "score_final": row.get("score_final"),
                    "versao_modelo": row.get("versao_modelo"),
                    "fonte_patrimonial": payload.get("fonte_patrimonial") or patrimonio.get("fonte_patrimonial"),
                    "usou_cvm_patrimonial": payload.get("usou_cvm_patrimonial") or patrimonio.get("usou_cvm"),
                    "fallback_patrimonial_usado": payload.get("fallback_patrimonial_usado") or patrimonio.get("fallback_usado"),
                    "gate55_status": gate55.get("status"),
                    "score_confianca_dados": payload.get("score_confianca_dados") or gate55.get("score_confianca_dados"),
                    "nivel_uso_dados": payload.get("nivel_uso_dados") or gate55.get("nivel_uso_dados"),
                }
            )

        return {"status": "ok", "quantidade": len(decisoes), "decisoes": decisoes}
    except Exception as erro:
        observabilidade.registrar_erro("api.auditoria.decisoes", erro)
        return {"status": "erro", "mensagem": str(erro), "decisoes": []}


@router.get("/taxa-acerto")
def obter_taxa_acerto() -> dict[str, Any]:
    """Retorna taxa de acerto nas janelas 90d e 365d."""
    try:
        return {
            "status": "ok",
            "taxa_acerto_90d": taxa_acerto(90),
            "taxa_acerto_365d": taxa_acerto(365),
        }
    except Exception as erro:
        observabilidade.registrar_erro("api.auditoria.taxa_acerto", erro)
        return {"status": "erro", "mensagem": str(erro)}


@router.get("/fallbacks")
def listar_fallbacks(limite: int = 100) -> dict[str, Any]:
    """Lista decisões em que o dado patrimonial veio de fallback auxiliar."""
    try:
        resultados = []
        for row in _listar_decisoes(limite):
            payload = _json_para_dict(row.get("payload_json"))
            patrimonio = payload.get("patrimonio_resolvido", {}) or {}
            fallback = payload.get("fallback_patrimonial_usado") or patrimonio.get("fallback_usado")
            if fallback:
                resultados.append(
                    {
                        "id": row.get("id"),
                        "ticker": row.get("ticker"),
                        "data_decisao": row.get("data_decisao"),
                        "decisao": row.get("decisao"),
                        "fonte_patrimonial": payload.get("fonte_patrimonial") or patrimonio.get("fonte_patrimonial"),
                        "motivo": row.get("motivo"),
                    }
                )

        return {"status": "ok", "quantidade": len(resultados), "fallbacks": resultados}
    except Exception as erro:
        observabilidade.registrar_erro("api.auditoria.fallbacks", erro)
        return {"status": "erro", "mensagem": str(erro), "fallbacks": []}


@router.get("/gate55")
def listar_gate55(limite: int = 100) -> dict[str, Any]:
    """Lista status do Gate 5.5 nas decisões recentes."""
    try:
        resultados = []
        resumo = defaultdict(int)

        for row in _listar_decisoes(limite):
            payload = _json_para_dict(row.get("payload_json"))
            gate55 = payload.get("gate55_confianca_dados", {}) or {}
            status_gate = gate55.get("status", "NAO_REGISTRADO")
            resumo[status_gate] += 1
            resultados.append(
                {
                    "id": row.get("id"),
                    "ticker": row.get("ticker"),
                    "data_decisao": row.get("data_decisao"),
                    "decisao": row.get("decisao"),
                    "gate55_status": status_gate,
                    "score_confianca_dados": gate55.get("score_confianca_dados"),
                    "nivel_uso_dados": gate55.get("nivel_uso_dados"),
                    "fonte_patrimonial": gate55.get("fonte_patrimonial"),
                    "motivo": gate55.get("motivo"),
                }
            )

        return {
            "status": "ok",
            "resumo": dict(resumo),
            "quantidade": len(resultados),
            "gate55": resultados,
        }
    except Exception as erro:
        observabilidade.registrar_erro("api.auditoria.gate55", erro)
        return {"status": "erro", "mensagem": str(erro), "gate55": []}


@router.get("/instabilidade")
def detectar_instabilidade(limite: int = 300) -> dict[str, Any]:
    """
    Detecta tickers com decisões divergentes em janelas próximas.

    Critério simples inicial:
    - mesmo ticker;
    - decisões recentes diferentes;
    - mudança entre ação ofensiva e defensiva.
    """
    ofensivas = {"COMPRAR", "COMPRAR_PARCIAL", "COMPRAR_PARCIALMENTE", "MANTER"}
    defensivas = {"EVITAR", "EVITAR_ENTRADA", "VENDER", "REDUZIR", "MONITORAR", "AGUARDAR"}

    try:
        por_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in _listar_decisoes(limite):
            ticker = row.get("ticker")
            if ticker:
                por_ticker[ticker].append(dict(row))

        instaveis = []
        for ticker, decisoes in por_ticker.items():
            if len(decisoes) < 2:
                continue
            recentes = decisoes[:5]
            classes = []
            for decisao in recentes:
                acao = str(decisao.get("decisao") or "").upper()
                if acao in ofensivas:
                    classes.append("OFENSIVA")
                elif acao in defensivas:
                    classes.append("DEFENSIVA")
                else:
                    classes.append("INDEFINIDA")

            if "OFENSIVA" in classes and "DEFENSIVA" in classes:
                instaveis.append(
                    {
                        "ticker": ticker,
                        "quantidade_decisoes_analisadas": len(recentes),
                        "classes_detectadas": sorted(set(classes)),
                        "decisoes": [
                            {
                                "id": d.get("id"),
                                "data_decisao": d.get("data_decisao"),
                                "decisao": d.get("decisao"),
                                "motivo": d.get("motivo"),
                            }
                            for d in recentes
                        ],
                    }
                )

        return {"status": "ok", "quantidade": len(instaveis), "instabilidades": instaveis}
    except Exception as erro:
        observabilidade.registrar_erro("api.auditoria.instabilidade", erro)
        return {"status": "erro", "mensagem": str(erro), "instabilidades": []}
