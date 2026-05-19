"""
api/auditoria.py

Endpoints de auditoria operacional do FIIA.
"""
from __future__ import annotations

import json
import secrets
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from banco import db
from aprendizado.avaliador import taxa_acerto
from sistema import observabilidade
from coleta import tabela_mestre_fiis, cvm_informe_mensal, cvm_fnet_documentos
from config.settings import FIIA_API_KEY
from decisao.auditoria_decisao import consultar_decisao_auditavel, listar_decisoes_auditaveis

router = APIRouter(prefix="/api/auditoria", tags=["auditoria"])


def verificar_api_key(x_api_key: str | None = Header(None)) -> None:
    """Protege endpoints sensíveis usando a autenticação por API key existente."""
    if not FIIA_API_KEY:
        raise HTTPException(status_code=500, detail="FIIA_API_KEY não configurada")
    if not x_api_key or not secrets.compare_digest(x_api_key, FIIA_API_KEY):
        raise HTTPException(status_code=401, detail="API Key inválida ou ausente")


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


def _parse_data_iso(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except Exception:
        return None


@router.get("/decisoes/auditaveis", dependencies=[Depends(verificar_api_key)])
def listar_decisoes_auditaveis_api(limite: int = 50) -> dict[str, Any]:
    """Lista decisões salvas com metadados de auditoria, sem disparar coleta."""
    try:
        return listar_decisoes_auditaveis(limite=limite)
    except Exception as erro:
        observabilidade.registrar_erro("api.auditoria.decisoes_auditaveis", erro)
        return {
            "status": "erro",
            "mensagem": "Falha controlada ao consultar decisões auditáveis.",
            "decisoes": [],
        }


@router.get("/decisoes/{decisao_id}/auditavel", dependencies=[Depends(verificar_api_key)])
def consultar_decisao_auditavel_api(
    decisao_id: int,
    incluir_payload: bool = True,
    replay: bool = False,
) -> dict[str, Any]:
    """
    Consulta decisão salva, payload auditável e replay opcional explícito.

    Não executa scraping, não reavalia ticker e não chama motor decisório.
    """
    try:
        resposta = consultar_decisao_auditavel(
            decisao_id,
            incluir_payload=incluir_payload,
            replay=replay,
        )
        if resposta.get("status") == "nao_encontrado":
            raise HTTPException(status_code=404, detail="Decisão não encontrada")
        return resposta
    except HTTPException:
        raise
    except Exception as erro:
        observabilidade.registrar_erro(
            "api.auditoria.decisao_auditavel",
            erro,
            contexto={"decisao_id": decisao_id},
        )
        return {
            "status": "erro",
            "mensagem": "Falha controlada ao consultar decisão auditável.",
            "decisao_id": decisao_id,
        }


@router.get("/decisoes")
def listar_decisoes(limite: int = 50) -> dict[str, Any]:
    try:
        decisoes = []
        for row in _listar_decisoes(limite):
            payload = _json_para_dict(row.get("payload_json"))
            gate55 = payload.get("gate55_confianca_dados", {}) or {}
            patrimonio = payload.get("patrimonio_resolvido", {}) or {}
            decisoes.append({
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
            })
        return {"status": "ok", "quantidade": len(decisoes), "decisoes": decisoes}
    except Exception as erro:
        observabilidade.registrar_erro("api.auditoria.decisoes", erro)
        return {"status": "erro", "mensagem": str(erro), "decisoes": []}


@router.get("/taxa-acerto")
def obter_taxa_acerto() -> dict[str, Any]:
    try:
        return {"status": "ok", "taxa_acerto_90d": taxa_acerto(90), "taxa_acerto_365d": taxa_acerto(365)}
    except Exception as erro:
        observabilidade.registrar_erro("api.auditoria.taxa_acerto", erro)
        return {"status": "erro", "mensagem": str(erro)}


@router.get("/fallbacks")
def listar_fallbacks(limite: int = 100) -> dict[str, Any]:
    try:
        resultados = []
        for row in _listar_decisoes(limite):
            payload = _json_para_dict(row.get("payload_json"))
            patrimonio = payload.get("patrimonio_resolvido", {}) or {}
            fallback = payload.get("fallback_patrimonial_usado") or patrimonio.get("fallback_usado")
            if fallback:
                resultados.append({
                    "id": row.get("id"),
                    "ticker": row.get("ticker"),
                    "data_decisao": row.get("data_decisao"),
                    "decisao": row.get("decisao"),
                    "fonte_patrimonial": payload.get("fonte_patrimonial") or patrimonio.get("fonte_patrimonial"),
                    "motivo": row.get("motivo"),
                })
        return {"status": "ok", "quantidade": len(resultados), "fallbacks": resultados}
    except Exception as erro:
        observabilidade.registrar_erro("api.auditoria.fallbacks", erro)
        return {"status": "erro", "mensagem": str(erro), "fallbacks": []}


@router.get("/gate55")
def listar_gate55(limite: int = 100) -> dict[str, Any]:
    try:
        resultados = []
        resumo = defaultdict(int)
        for row in _listar_decisoes(limite):
            payload = _json_para_dict(row.get("payload_json"))
            gate55 = payload.get("gate55_confianca_dados", {}) or {}
            status_gate = gate55.get("status", "NAO_REGISTRADO")
            resumo[status_gate] += 1
            resultados.append({
                "id": row.get("id"),
                "ticker": row.get("ticker"),
                "data_decisao": row.get("data_decisao"),
                "decisao": row.get("decisao"),
                "gate55_status": status_gate,
                "score_confianca_dados": gate55.get("score_confianca_dados"),
                "nivel_uso_dados": gate55.get("nivel_uso_dados"),
                "fonte_patrimonial": gate55.get("fonte_patrimonial"),
                "motivo": gate55.get("motivo"),
            })
        return {"status": "ok", "resumo": dict(resumo), "quantidade": len(resultados), "gate55": resultados}
    except Exception as erro:
        observabilidade.registrar_erro("api.auditoria.gate55", erro)
        return {"status": "erro", "mensagem": str(erro), "gate55": []}


@router.get("/cobertura-fnet")
def cobertura_fnet(limite: int = 500) -> dict[str, Any]:
    """Mede especificamente a cobertura documental FNET e idade da última importação."""
    try:
        tabela_mestre_fiis.garantir_tabela()
        cvm_fnet_documentos.garantir_tabela()
        base = db.buscar_todos(
            """
            SELECT ticker, cnpj_fundo, cnpj_classe, razao_social, nome_fundo
            FROM fiia_tabela_mestre_fiis
            ORDER BY ticker
            LIMIT ?
            """,
            (limite,),
        )
        meta = db.buscar_um(
            f"""
            SELECT MAX(coletado_em) AS ultima_importacao,
                   COUNT(*) AS total_documentos,
                   COUNT(DISTINCT ticker) AS tickers_com_documentos,
                   COUNT(DISTINCT cnpj_fundo) AS cnpjs_com_documentos
            FROM {cvm_fnet_documentos.TABELA}
            """
        )
        arquivos_rows = db.buscar_todos(
            f"""
            SELECT arquivo_origem, MAX(coletado_em) AS ultima_importacao, COUNT(*) AS registros
            FROM {cvm_fnet_documentos.TABELA}
            GROUP BY arquivo_origem
            ORDER BY ultima_importacao DESC
            LIMIT 10
            """
        )
        ultima_importacao = meta["ultima_importacao"] if meta else None
        dt_ultima = _parse_data_iso(ultima_importacao)
        dias_desde = None
        if dt_ultima:
            if dt_ultima.tzinfo is None:
                dt_ultima = dt_ultima.replace(tzinfo=timezone.utc)
            dias_desde = (datetime.now(timezone.utc) - dt_ultima).days
        ativos = []
        com_fnet = 0
        sem_fnet = 0
        for row in base:
            item = dict(row)
            cnpj = item.get("cnpj_fundo")
            documento = cvm_fnet_documentos.ultimo_documento_por_cnpj(cnpj) if cnpj else None
            tem_fnet = bool(documento)
            com_fnet += 1 if tem_fnet else 0
            sem_fnet += 0 if tem_fnet else 1
            ativos.append({
                "ticker": item.get("ticker"),
                "cnpj_fundo": cnpj,
                "cnpj_classe": item.get("cnpj_classe"),
                "tem_fnet_documental": tem_fnet,
                "ultimo_documento_fnet": documento.get("data_entrega") if documento else None,
                "tipo_ultimo_documento": documento.get("tipo_documento") if documento else None,
                "categoria_ultimo_documento": documento.get("categoria") if documento else None,
                "arquivo_origem_ultimo_documento": documento.get("arquivo_origem") if documento else None,
            })
        total_base = len(base)
        pct_com_fnet = round(com_fnet / total_base * 100, 2) if total_base else 0.0
        pct_sem_fnet = round(sem_fnet / total_base * 100, 2) if total_base else 0.0
        return {
            "status": "ok",
            "resumo": {
                "total_tabela_mestre": total_base,
                "total_documentos_fnet": meta["total_documentos"] if meta else 0,
                "tickers_com_documentos_no_banco": meta["tickers_com_documentos"] if meta else 0,
                "cnpjs_com_documentos_no_banco": meta["cnpjs_com_documentos"] if meta else 0,
                "ativos_com_fnet": com_fnet,
                "ativos_com_fnet_pct": pct_com_fnet,
                "ativos_sem_fnet": sem_fnet,
                "ativos_sem_fnet_pct": pct_sem_fnet,
                "ultima_importacao": ultima_importacao,
                "dias_desde_ultima_importacao": dias_desde,
                "base_fnet_vazia": not bool(meta and meta["total_documentos"]),
            },
            "arquivos_importados_recentes": [dict(row) for row in arquivos_rows],
            "ativos": ativos,
            "ativos_sem_fnet": [item for item in ativos if not item.get("tem_fnet_documental")],
        }
    except Exception as erro:
        observabilidade.registrar_erro("api.auditoria.cobertura_fnet", erro)
        return {"status": "erro", "mensagem": str(erro), "resumo": {}, "ativos": []}


@router.get("/cobertura-institucional")
def cobertura_institucional(limite: int = 500) -> dict[str, Any]:
    """Mede cobertura ticker -> CNPJ -> CVM patrimonial -> FNET documental."""
    try:
        tabela_mestre_fiis.garantir_tabela()
        cvm_informe_mensal.garantir_tabela()
        cvm_fnet_documentos.garantir_tabela()
        rows = db.buscar_todos(
            """
            SELECT ticker, cnpj_fundo, cnpj_classe, razao_social, nome_fundo
            FROM fiia_tabela_mestre_fiis
            ORDER BY ticker
            LIMIT ?
            """,
            (limite,),
        )
        ativos = []
        total = len(rows)
        com_cnpj = com_cvm = com_fnet = 0
        for row in rows:
            item = dict(row)
            cnpj = item.get("cnpj_fundo")
            informe = cvm_informe_mensal.ultimo_por_cnpj(cnpj) if cnpj else None
            documento = cvm_fnet_documentos.ultimo_documento_por_cnpj(cnpj) if cnpj else None
            if cnpj:
                com_cnpj += 1
            if informe:
                com_cvm += 1
            if documento:
                com_fnet += 1
            ativos.append({
                "ticker": item.get("ticker"),
                "cnpj_fundo": cnpj,
                "cnpj_classe": item.get("cnpj_classe"),
                "tem_cnpj": bool(cnpj),
                "tem_cvm_patrimonial": bool(informe),
                "competencia_cvm": informe.get("competencia") if informe else None,
                "tem_fnet_documental": bool(documento),
                "ultimo_documento_fnet": documento.get("data_entrega") if documento else None,
                "tipo_ultimo_documento": documento.get("tipo_documento") if documento else None,
            })
        def pct(valor: int) -> float:
            return round(valor / total * 100, 2) if total else 0.0
        return {"status": "ok", "resumo": {"total_tabela_mestre": total, "com_cnpj": com_cnpj, "com_cnpj_pct": pct(com_cnpj), "com_cvm_patrimonial": com_cvm, "com_cvm_patrimonial_pct": pct(com_cvm), "com_fnet_documental": com_fnet, "com_fnet_documental_pct": pct(com_fnet)}, "ativos": ativos}
    except Exception as erro:
        observabilidade.registrar_erro("api.auditoria.cobertura_institucional", erro)
        return {"status": "erro", "mensagem": str(erro), "resumo": {}, "ativos": []}


@router.get("/ativos-sem-cobertura")
def ativos_sem_cobertura(limite: int = 500) -> dict[str, Any]:
    try:
        cobertura = cobertura_institucional(limite=limite)
        problemas = []
        for item in cobertura.get("ativos", []):
            faltas = []
            if not item.get("tem_cnpj"):
                faltas.append("SEM_CNPJ")
            if not item.get("tem_cvm_patrimonial"):
                faltas.append("SEM_CVM_PATRIMONIAL")
            if not item.get("tem_fnet_documental"):
                faltas.append("SEM_FNET_DOCUMENTAL")
            if faltas:
                problemas.append({**item, "faltas": faltas})
        return {"status": "ok", "quantidade": len(problemas), "ativos": problemas}
    except Exception as erro:
        observabilidade.registrar_erro("api.auditoria.ativos_sem_cobertura", erro)
        return {"status": "erro", "mensagem": str(erro), "ativos": []}


@router.get("/instabilidade")
def detectar_instabilidade(limite: int = 300) -> dict[str, Any]:
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
                instaveis.append({"ticker": ticker, "quantidade_decisoes_analisadas": len(recentes), "classes_detectadas": sorted(set(classes)), "decisoes": [{"id": d.get("id"), "data_decisao": d.get("data_decisao"), "decisao": d.get("decisao"), "motivo": d.get("motivo")} for d in recentes]})
        return {"status": "ok", "quantidade": len(instaveis), "instabilidades": instaveis}
    except Exception as erro:
        observabilidade.registrar_erro("api.auditoria.instabilidade", erro)
        return {"status": "erro", "mensagem": str(erro), "instabilidades": []}
