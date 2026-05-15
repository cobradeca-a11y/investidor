"""
processamento/eventos_fnet.py

Leitura operacional de documentos FNET/CVM.
"""
from __future__ import annotations

import json
from datetime import datetime, date, timedelta
from typing import Any

from aprendizado.tentativa_erro import registrar_simulacao
from coleta import cvm_fnet_documentos, tabela_mestre_fiis
from sistema import observabilidade

TERMOS_RISCO_ALTO = [
    "fato relevante",
    "inadimpl",
    "vacância",
    "vacancia",
    "renúncia",
    "renuncia",
    "destituição",
    "destituicao",
    "liquidação",
    "liquidacao",
    "assembleia",
    "amortização extraordinária",
    "amortizacao extraordinaria",
    "reavaliação",
    "reavaliacao",
    "risco",
    "default",
]

TERMOS_RISCO_MEDIO = [
    "comunicado",
    "emissão",
    "emissao",
    "oferta",
    "subscrição",
    "subscricao",
    "rendimento",
    "relatório gerencial",
    "relatorio gerencial",
    "informe",
]

ACOES_FORTES = {"COMPRAR", "COMPRAR_PARCIAL", "COMPRAR_PARCIALMENTE"}


def _parse_data(valor: str | None) -> date | None:
    if not valor:
        return None
    texto = str(valor).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(texto, fmt).date()
        except Exception:
            pass
    try:
        return date.fromisoformat(texto)
    except Exception:
        return None


def _texto_documento(doc: dict[str, Any]) -> str:
    partes = [doc.get("categoria"), doc.get("tipo_documento"), doc.get("assunto")]
    return " ".join(str(p or "") for p in partes).lower()


def classificar_documento(doc: dict[str, Any], dias_recencia: int = 90) -> dict[str, Any]:
    texto = _texto_documento(doc)
    data_doc = _parse_data(doc.get("data_entrega") or doc.get("data_referencia"))
    recente = bool(data_doc and data_doc >= date.today() - timedelta(days=dias_recencia))

    termos_alto = [termo for termo in TERMOS_RISCO_ALTO if termo in texto]
    termos_medio = [termo for termo in TERMOS_RISCO_MEDIO if termo in texto]

    if termos_alto and recente:
        nivel = "ALTO"
    elif termos_alto:
        nivel = "MEDIO"
    elif termos_medio and recente:
        nivel = "MEDIO"
    else:
        nivel = "BAIXO"

    return {
        "documento_id": doc.get("id"),
        "data_documento": data_doc.isoformat() if data_doc else None,
        "recente": recente,
        "nivel_risco_documental": nivel,
        "termos_risco_alto": termos_alto,
        "termos_risco_medio": termos_medio,
        "categoria": doc.get("categoria"),
        "tipo_documento": doc.get("tipo_documento"),
        "assunto": doc.get("assunto"),
        "url_documento": doc.get("url_documento"),
    }


def calcular_score_documental(classificados: list[dict[str, Any]], possui_fnet: bool) -> dict[str, Any]:
    if not possui_fnet:
        return {
            "score_documental_fnet": 40,
            "penalizacao_score": 5,
            "bonificacao_score": 0,
            "motivo_score_documental": "Sem documentos FNET disponíveis para o ativo.",
        }

    altos = [d for d in classificados if d.get("nivel_risco_documental") == "ALTO"]
    medios = [d for d in classificados if d.get("nivel_risco_documental") == "MEDIO"]
    recentes = [d for d in classificados if d.get("recente")]

    score = 100
    penalizacao = 0
    bonificacao = 0
    motivos = []

    if altos:
        perda = min(60, 30 * len(altos))
        score -= perda
        penalizacao += perda
        motivos.append(f"{len(altos)} documento(s) de risco alto.")

    if medios:
        perda = min(30, 10 * len(medios))
        score -= perda
        penalizacao += perda
        motivos.append(f"{len(medios)} documento(s) de risco médio.")

    if recentes and not altos:
        bonificacao += 3
        motivos.append("Há documentação recente sem risco alto identificado.")

    score = max(0, min(100, score + bonificacao))

    return {
        "score_documental_fnet": score,
        "penalizacao_score": penalizacao,
        "bonificacao_score": bonificacao,
        "motivo_score_documental": " ".join(motivos) if motivos else "Documentação FNET sem alerta relevante.",
    }


def analisar_eventos_ticker(ticker: str, limite: int = 20, dias_recencia: int = 90) -> dict[str, Any]:
    ticker_norm = ticker.upper().replace(".SA", "").strip()

    try:
        docs = cvm_fnet_documentos.listar_por_ticker(ticker_norm, limite=limite)

        if not docs:
            identidade = tabela_mestre_fiis.obter_por_ticker(ticker_norm)
            cnpj = identidade.get("cnpj_fundo") if identidade else None
            docs = cvm_fnet_documentos.listar_por_cnpj(cnpj, limite=limite) if cnpj else []

        classificados = [classificar_documento(doc, dias_recencia=dias_recencia) for doc in docs]
        risco_alto = [item for item in classificados if item["nivel_risco_documental"] == "ALTO"]
        risco_medio = [item for item in classificados if item["nivel_risco_documental"] == "MEDIO"]
        score_doc = calcular_score_documental(classificados, possui_fnet=bool(docs))

        if risco_alto:
            nivel = "ALTO"
        elif risco_medio:
            nivel = "MEDIO"
        elif docs:
            nivel = "BAIXO"
        else:
            nivel = "SEM_FNET"

        resumo = {
            "ticker": ticker_norm,
            "nivel_risco_documental": nivel,
            "documentos_analisados": len(docs),
            "documentos_risco_alto": len(risco_alto),
            "documentos_risco_medio": len(risco_medio),
            "eventos_relevantes": risco_alto + risco_medio,
            **score_doc,
        }

        observabilidade.registrar_evento(
            "INFO",
            "processamento.eventos_fnet",
            "Eventos FNET analisados",
            ticker=ticker_norm,
            contexto={
                "nivel_risco_documental": nivel,
                "documentos_analisados": len(docs),
                "score_documental_fnet": score_doc.get("score_documental_fnet"),
            },
        )
        return resumo

    except Exception as erro:
        observabilidade.registrar_erro("processamento.eventos_fnet", erro, ticker=ticker_norm)
        return {
            "ticker": ticker_norm,
            "nivel_risco_documental": "ERRO",
            "documentos_analisados": 0,
            "documentos_risco_alto": 0,
            "documentos_risco_medio": 0,
            "eventos_relevantes": [],
            "score_documental_fnet": 0,
            "penalizacao_score": 100,
            "bonificacao_score": 0,
            "motivo_score_documental": str(erro),
            "erro": str(erro),
        }


def registrar_evidencia_fnet_aprendizado(veredito: dict[str, Any], eventos: dict[str, Any]) -> dict[str, Any] | None:
    """Registra a decisão ajustada por FNET como simulação rastreável."""
    ticker = veredito.get("ticker") or eventos.get("ticker")
    if not ticker:
        return None

    try:
        payload = {
            "origem": "FNET",
            "risco_documental_fnet": eventos.get("nivel_risco_documental"),
            "score_documental_fnet": eventos.get("score_documental_fnet"),
            "ajuste_score_fnet": veredito.get("ajuste_score_fnet"),
            "score_final_original": veredito.get("score_final_original"),
            "score_final": veredito.get("score_final"),
            "eventos_relevantes": eventos.get("eventos_relevantes", []),
            "motivo_score_documental": eventos.get("motivo_score_documental"),
        }

        simulacao = registrar_simulacao(
            ticker=ticker,
            acao_simulada=veredito.get("decisao", "MONITORAR"),
            decisao_origem="DECISAO_COM_FNET",
            segmento=veredito.get("segmento"),
            score_final=veredito.get("score_final"),
            confianca=veredito.get("confianca"),
            risco=veredito.get("risco_documental_fnet") or veredito.get("risco"),
            fonte_patrimonial=veredito.get("fonte_patrimonial"),
            gate55_status=(veredito.get("gate55_confianca_dados") or {}).get("status"),
            peso_versao="fnet_score_v1",
            payload_json=json.dumps(payload, ensure_ascii=False, default=str),
        )
        veredito["aprendizado_fnet_simulacao_id"] = simulacao.get("id")
        return simulacao
    except Exception as erro:
        observabilidade.registrar_erro("processamento.eventos_fnet.aprendizado", erro, ticker=ticker)
        veredito["aprendizado_fnet_erro"] = str(erro)
        return None


def aplicar_eventos_na_decisao(veredito: dict[str, Any], eventos: dict[str, Any]) -> dict[str, Any]:
    decisao = str(veredito.get("decisao") or "MONITORAR").upper()
    nivel = eventos.get("nivel_risco_documental")
    penalizacao = float(eventos.get("penalizacao_score") or 0)
    bonificacao = float(eventos.get("bonificacao_score") or 0)

    veredito["eventos_fnet"] = eventos
    veredito["risco_documental_fnet"] = nivel
    veredito["score_documental_fnet"] = eventos.get("score_documental_fnet")
    veredito["ajuste_score_fnet"] = round(bonificacao - penalizacao, 2)

    score_original = veredito.get("score_final")
    if score_original is not None:
        try:
            veredito["score_final_original"] = score_original
            veredito["score_final"] = max(0, round(float(score_original) + bonificacao - penalizacao, 2))
        except Exception:
            pass

    trilha = veredito.setdefault("trilha_gates", [])
    marcador = f"FNET:{nivel}:score={eventos.get('score_documental_fnet')}"
    if marcador not in trilha:
        trilha.append(marcador)

    if nivel == "ALTO" and decisao in ACOES_FORTES:
        veredito.setdefault("decisao_original", decisao)
        veredito["decisao"] = "MONITORAR"
        veredito["motivo"] = (
            f"{veredito.get('motivo', '')} Compra forte bloqueada por evento FNET recente de risco alto. "
            f"Ajuste score FNET: {veredito.get('ajuste_score_fnet')}."
        ).strip()
    elif nivel == "MEDIO" and decisao == "COMPRAR":
        veredito.setdefault("decisao_original", decisao)
        veredito["decisao"] = "COMPRAR_PARCIAL"
        veredito["motivo"] = (
            f"{veredito.get('motivo', '')} Compra rebaixada por evento FNET de risco médio. "
            f"Ajuste score FNET: {veredito.get('ajuste_score_fnet')}."
        ).strip()

    registrar_evidencia_fnet_aprendizado(veredito, eventos)
    return veredito
