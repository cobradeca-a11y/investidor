"""
processamento/eventos_fnet.py

Leitura operacional de documentos FNET/CVM.

Objetivo:
- transformar metadados FNET em sinais de risco;
- identificar documentos potencialmente estruturais;
- rebaixar compras fortes quando houver evento sensível recente;
- preservar rastreabilidade sem depender de IA externa.
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Any

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
    partes = [
        doc.get("categoria"),
        doc.get("tipo_documento"),
        doc.get("assunto"),
    ]
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
        }

        observabilidade.registrar_evento(
            "INFO",
            "processamento.eventos_fnet",
            "Eventos FNET analisados",
            ticker=ticker_norm,
            contexto={"nivel_risco_documental": nivel, "documentos_analisados": len(docs)},
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
            "erro": str(erro),
        }


def aplicar_eventos_na_decisao(veredito: dict[str, Any], eventos: dict[str, Any]) -> dict[str, Any]:
    """Rebaixa decisão quando houver risco documental sensível."""
    decisao = str(veredito.get("decisao") or "MONITORAR").upper()
    nivel = eventos.get("nivel_risco_documental")

    veredito["eventos_fnet"] = eventos
    veredito["risco_documental_fnet"] = nivel

    trilha = veredito.setdefault("trilha_gates", [])
    marcador = f"FNET:{nivel}"
    if marcador not in trilha:
        trilha.append(marcador)

    if nivel == "ALTO" and decisao in ACOES_FORTES:
        veredito.setdefault("decisao_original", decisao)
        veredito["decisao"] = "MONITORAR"
        veredito["motivo"] = (
            f"{veredito.get('motivo', '')} Compra forte bloqueada por evento FNET recente de risco alto."
        ).strip()
    elif nivel == "MEDIO" and decisao == "COMPRAR":
        veredito.setdefault("decisao_original", decisao)
        veredito["decisao"] = "COMPRAR_PARCIAL"
        veredito["motivo"] = (
            f"{veredito.get('motivo', '')} Compra rebaixada por evento FNET de risco médio."
        ).strip()

    return veredito
