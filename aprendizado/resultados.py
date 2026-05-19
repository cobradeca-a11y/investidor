"""
aprendizado/resultados.py

Avaliação temporal de resultados observados do FIIA.

Regras:
- suporta janelas 30, 90, 180 e 365 dias;
- detecta falso positivo e falso negativo;
- não altera thresholds, motor ou contrato final da decisão;
- não aciona rede; recebe preços/benchmarks observados como entrada.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from banco import db
from config import settings
from sistema import observabilidade

TABELA_RESULTADOS_OPERACIONAIS = "aprendizado_resultados_operacionais"
JANELAS_SUPORTADAS = tuple(settings.JANELAS_AVALIACAO_DIAS)
ACOES_OFENSIVAS = {"COMPRAR", "COMPRAR_PARCIAL", "COMPRAR_PARCIALMENTE", "MANTER"}
ACOES_DEFENSIVAS = {"EVITAR", "EVITAR_ENTRADA", "MONITORAR", "AGUARDAR", "REDUZIR", "VENDER", "BLOQUEAR_APORTE"}


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data_iso(valor: str | date | datetime | None) -> str:
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if valor:
        return str(valor)[:10]
    return date.today().isoformat()


def _normalizar_ticker(ticker: str) -> str:
    return ticker.upper().replace(".SA", "").strip()


def _normalizar_acao(acao: str | None) -> str:
    acao_norm = str(acao or "MONITORAR").upper().strip()
    if acao_norm in ACOES_OFENSIVAS or acao_norm in ACOES_DEFENSIVAS:
        return acao_norm
    return "MONITORAR"


def garantir_tabela_resultados_operacionais() -> None:
    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA_RESULTADOS_OPERACIONAIS} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            simulacao_id INTEGER,
            ticker TEXT NOT NULL,
            data_decisao TEXT NOT NULL,
            data_avaliacao TEXT NOT NULL,
            janela_dias INTEGER NOT NULL,
            acao_original TEXT NOT NULL,
            preco_entrada REAL,
            preco_saida REAL,
            retorno_preco_pct REAL,
            retorno_dividendos_pct REAL,
            retorno_total_pct REAL,
            benchmark_pct REAL,
            superou_benchmark INTEGER,
            resultado TEXT NOT NULL,
            falso_positivo INTEGER NOT NULL DEFAULT 0,
            falso_negativo INTEGER NOT NULL DEFAULT 0,
            evidencia_json TEXT,
            criado_em TEXT NOT NULL
        )
        """
    )
    db.executar(
        f"CREATE INDEX IF NOT EXISTS idx_{TABELA_RESULTADOS_OPERACIONAIS}_ticker_janela ON {TABELA_RESULTADOS_OPERACIONAIS}(ticker, janela_dias)"
    )
    db.executar(
        f"CREATE INDEX IF NOT EXISTS idx_{TABELA_RESULTADOS_OPERACIONAIS}_resultado ON {TABELA_RESULTADOS_OPERACIONAIS}(resultado)"
    )


def validar_janela(janela_dias: int) -> int:
    janela = int(janela_dias)
    if janela not in JANELAS_SUPORTADAS:
        raise ValueError(f"Janela não suportada: {janela}. Use {list(JANELAS_SUPORTADAS)}.")
    return janela


def classificar_resultado_operacional(
    *,
    acao_original: str,
    retorno_total_pct: float,
    benchmark_pct: float | None,
) -> dict[str, Any]:
    """Classifica acerto, falso positivo ou falso negativo sem alterar decisão."""
    acao = _normalizar_acao(acao_original)
    retorno = float(retorno_total_pct)
    benchmark = float(benchmark_pct) if benchmark_pct is not None else 0.0
    superou = retorno > benchmark

    falso_positivo = acao in ACOES_OFENSIVAS and not superou
    falso_negativo = acao in ACOES_DEFENSIVAS and superou

    if falso_positivo:
        resultado = "FALSO_POSITIVO"
    elif falso_negativo:
        resultado = "FALSO_NEGATIVO"
    elif superou:
        resultado = "ACERTO"
    else:
        resultado = "ERRO"

    return {
        "acao_original": acao,
        "superou_benchmark": superou,
        "resultado": resultado,
        "falso_positivo": falso_positivo,
        "falso_negativo": falso_negativo,
    }


def avaliar_resultado_temporal(
    *,
    ticker: str,
    acao_original: str,
    data_decisao: str | date | datetime,
    data_avaliacao: str | date | datetime,
    janela_dias: int,
    preco_entrada: float,
    preco_saida: float,
    dividendos_pct: float = 0.0,
    benchmark_pct: float | None = None,
    simulacao_id: int | None = None,
    evidencia: dict[str, Any] | None = None,
    persistir: bool = True,
) -> dict[str, Any]:
    """Avalia resultado observado em uma janela temporal suportada."""
    janela = validar_janela(janela_dias)
    retorno_preco_pct = ((float(preco_saida) / float(preco_entrada)) - 1.0) * 100.0
    retorno_total_pct = retorno_preco_pct + float(dividendos_pct or 0.0)
    classificacao = classificar_resultado_operacional(
        acao_original=acao_original,
        retorno_total_pct=retorno_total_pct,
        benchmark_pct=benchmark_pct,
    )
    payload_evidencia = {
        "ticker": _normalizar_ticker(ticker),
        "janela_dias": janela,
        "preco_entrada": preco_entrada,
        "preco_saida": preco_saida,
        "dividendos_pct": dividendos_pct,
        "benchmark_pct": benchmark_pct,
        **(evidencia or {}),
    }
    registro = {
        "simulacao_id": simulacao_id,
        "ticker": _normalizar_ticker(ticker),
        "data_decisao": _data_iso(data_decisao),
        "data_avaliacao": _data_iso(data_avaliacao),
        "janela_dias": janela,
        "acao_original": classificacao["acao_original"],
        "preco_entrada": float(preco_entrada),
        "preco_saida": float(preco_saida),
        "retorno_preco_pct": round(retorno_preco_pct, 4),
        "retorno_dividendos_pct": round(float(dividendos_pct or 0.0), 4),
        "retorno_total_pct": round(retorno_total_pct, 4),
        "benchmark_pct": round(float(benchmark_pct), 4) if benchmark_pct is not None else None,
        "superou_benchmark": bool(classificacao["superou_benchmark"]),
        "resultado": classificacao["resultado"],
        "falso_positivo": bool(classificacao["falso_positivo"]),
        "falso_negativo": bool(classificacao["falso_negativo"]),
        "evidencia": payload_evidencia,
        "criado_em": _agora_iso(),
    }

    observabilidade.registrar_evento(
        "INFO",
        "aprendizado.resultados",
        "Resultado temporal avaliado",
        ticker=registro["ticker"],
        contexto={
            "janela_dias": janela,
            "resultado": registro["resultado"],
            "falso_positivo": registro["falso_positivo"],
            "falso_negativo": registro["falso_negativo"],
        },
    )

    if persistir:
        garantir_tabela_resultados_operacionais()
        db.executar(
            f"""
            INSERT INTO {TABELA_RESULTADOS_OPERACIONAIS}
            (simulacao_id, ticker, data_decisao, data_avaliacao, janela_dias, acao_original,
             preco_entrada, preco_saida, retorno_preco_pct, retorno_dividendos_pct, retorno_total_pct,
             benchmark_pct, superou_benchmark, resultado, falso_positivo, falso_negativo,
             evidencia_json, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                registro["simulacao_id"],
                registro["ticker"],
                registro["data_decisao"],
                registro["data_avaliacao"],
                registro["janela_dias"],
                registro["acao_original"],
                registro["preco_entrada"],
                registro["preco_saida"],
                registro["retorno_preco_pct"],
                registro["retorno_dividendos_pct"],
                registro["retorno_total_pct"],
                registro["benchmark_pct"],
                int(registro["superou_benchmark"]),
                registro["resultado"],
                int(registro["falso_positivo"]),
                int(registro["falso_negativo"]),
                json.dumps(registro["evidencia"], ensure_ascii=False, sort_keys=True, default=str),
                registro["criado_em"],
            ),
        )
    return registro


def resumir_resultados_operacionais(janela_dias: int | None = None) -> dict[str, Any]:
    garantir_tabela_resultados_operacionais()
    if janela_dias is None:
        rows = db.buscar_todos(f"SELECT * FROM {TABELA_RESULTADOS_OPERACIONAIS}")
        janela = None
    else:
        janela = validar_janela(janela_dias)
        rows = db.buscar_todos(
            f"SELECT * FROM {TABELA_RESULTADOS_OPERACIONAIS} WHERE janela_dias = ?",
            (janela,),
        )
    total = len(rows)
    falsos_positivos = sum(int(row["falso_positivo"] or 0) for row in rows)
    falsos_negativos = sum(int(row["falso_negativo"] or 0) for row in rows)
    acertos = sum(1 for row in rows if row["resultado"] == "ACERTO")
    return {
        "janela_dias": janela,
        "total": total,
        "acertos": acertos,
        "acerto_pct": round((acertos / total) * 100, 2) if total else 0.0,
        "falsos_positivos": falsos_positivos,
        "falsos_positivos_pct": round((falsos_positivos / total) * 100, 2) if total else 0.0,
        "falsos_negativos": falsos_negativos,
        "falsos_negativos_pct": round((falsos_negativos / total) * 100, 2) if total else 0.0,
    }
