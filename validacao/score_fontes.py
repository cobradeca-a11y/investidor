"""
validacao/score_fontes.py

Histórico longitudinal de confiabilidade por fonte.

Regras:
- não altera decisão automaticamente;
- score é insumo auditável, não regra oculta;
- não aciona rede;
- registros contêm fonte, ticker, data, status, score e motivo.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from statistics import mean
from typing import Any

from banco import db
from sistema import observabilidade
from validacao.governanca_fontes import STATUS_VALIDOS, STATUS_SUSPEITA

TABELA_SCORE_FONTES = "governanca_fontes_score_historico"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalizar_data(valor: str | date | datetime | None) -> str:
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if valor:
        return str(valor)[:10]
    return date.today().isoformat()


def _normalizar_ticker(ticker: str | None) -> str | None:
    if not ticker:
        return None
    return ticker.upper().replace(".SA", "").strip()


def _normalizar_score(score: float | int | None) -> float:
    try:
        return round(max(0.0, min(100.0, float(score if score is not None else 0.0))), 2)
    except Exception:
        return 0.0


def garantir_tabela_score_fontes() -> None:
    """Cria tabela aditiva de score histórico de fontes."""
    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA_SCORE_FONTES} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fonte TEXT NOT NULL,
            ticker TEXT,
            data_referencia TEXT NOT NULL,
            status TEXT NOT NULL,
            score_confianca_fonte REAL NOT NULL,
            motivo TEXT,
            payload_json TEXT,
            criado_em TEXT NOT NULL,
            CHECK(status IN ('OK', 'VENCIDA', 'DIVERGENTE', 'INDISPONIVEL', 'SUSPEITA'))
        )
        """
    )
    db.executar(
        f"CREATE INDEX IF NOT EXISTS idx_{TABELA_SCORE_FONTES}_fonte_data ON {TABELA_SCORE_FONTES}(fonte, data_referencia)"
    )
    db.executar(
        f"CREATE INDEX IF NOT EXISTS idx_{TABELA_SCORE_FONTES}_ticker_data ON {TABELA_SCORE_FONTES}(ticker, data_referencia)"
    )


def registrar_score_fonte(
    *,
    fonte: str,
    status: str,
    score: float | int,
    motivo: str,
    ticker: str | None = None,
    data_referencia: str | date | datetime | None = None,
    payload: dict[str, Any] | None = None,
    persistir: bool = True,
) -> dict[str, Any]:
    """Registra um ponto histórico de confiabilidade de fonte."""
    fonte_norm = fonte.upper().strip()
    status_norm = status.upper().strip() if status else STATUS_SUSPEITA
    if status_norm not in STATUS_VALIDOS:
        status_norm = STATUS_SUSPEITA

    registro = {
        "fonte": fonte_norm,
        "ticker": _normalizar_ticker(ticker),
        "data_referencia": _normalizar_data(data_referencia),
        "status": status_norm,
        "score_confianca_fonte": _normalizar_score(score),
        "motivo": motivo or "Sem motivo informado.",
        "payload": payload or {},
        "criado_em": _agora_iso(),
    }

    observabilidade.registrar_evento(
        "INFO" if status_norm == "OK" else "WARN",
        "validacao.score_fontes",
        "Score histórico de fonte registrado",
        ticker=registro.get("ticker"),
        fonte=fonte_norm,
        contexto={
            "status": status_norm,
            "score_confianca_fonte": registro["score_confianca_fonte"],
            "data_referencia": registro["data_referencia"],
        },
    )

    if persistir:
        garantir_tabela_score_fontes()
        db.executar(
            f"""
            INSERT INTO {TABELA_SCORE_FONTES}
            (fonte, ticker, data_referencia, status, score_confianca_fonte, motivo, payload_json, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                registro["fonte"],
                registro["ticker"],
                registro["data_referencia"],
                registro["status"],
                registro["score_confianca_fonte"],
                registro["motivo"],
                json.dumps(registro["payload"], ensure_ascii=False, sort_keys=True, default=str),
                registro["criado_em"],
            ),
        )
    return registro


def registrar_score_a_partir_status(
    status_fonte: dict[str, Any],
    *,
    ticker: str | None = None,
    data_referencia: str | date | datetime | None = None,
    persistir: bool = True,
) -> dict[str, Any]:
    """Converte payload de governança instantânea em registro histórico."""
    return registrar_score_fonte(
        fonte=status_fonte.get("fonte") or "INDEFINIDA",
        status=status_fonte.get("status") or STATUS_SUSPEITA,
        score=status_fonte.get("score_confianca_fonte"),
        motivo=status_fonte.get("motivo") or "Status de fonte sem motivo informado.",
        ticker=ticker or status_fonte.get("ticker"),
        data_referencia=data_referencia or status_fonte.get("data_referencia"),
        payload=status_fonte,
        persistir=persistir,
    )


def consultar_historico_fonte(
    fonte: str,
    *,
    ticker: str | None = None,
    limite: int = 100,
) -> list[dict[str, Any]]:
    """Consulta histórico persistido de score por fonte, opcionalmente por ticker."""
    garantir_tabela_score_fontes()
    fonte_norm = fonte.upper().strip()
    limite_seguro = max(1, min(int(limite or 100), 1000))
    if ticker:
        rows = db.buscar_todos(
            f"""
            SELECT * FROM {TABELA_SCORE_FONTES}
            WHERE fonte = ? AND ticker = ?
            ORDER BY data_referencia DESC, criado_em DESC
            LIMIT ?
            """,
            (fonte_norm, _normalizar_ticker(ticker), limite_seguro),
        )
    else:
        rows = db.buscar_todos(
            f"""
            SELECT * FROM {TABELA_SCORE_FONTES}
            WHERE fonte = ?
            ORDER BY data_referencia DESC, criado_em DESC
            LIMIT ?
            """,
            (fonte_norm, limite_seguro),
        )
    return [dict(row) for row in rows]


def resumir_confiabilidade_fonte(
    fonte: str,
    *,
    ticker: str | None = None,
    limite: int = 100,
) -> dict[str, Any]:
    """Resume confiabilidade histórica como auditoria, sem alterar decisão."""
    historico = consultar_historico_fonte(fonte, ticker=ticker, limite=limite)
    if not historico:
        return {
            "fonte": fonte.upper().strip(),
            "ticker": _normalizar_ticker(ticker),
            "quantidade": 0,
            "score_medio": None,
            "ultimo_status": None,
            "ultimo_score": None,
            "status_distribuicao": {},
            "uso": "AUDITORIA_APENAS",
            "altera_decisao_automaticamente": False,
        }

    scores = [float(item.get("score_confianca_fonte") or 0.0) for item in historico]
    distribuicao: dict[str, int] = {}
    for item in historico:
        status = str(item.get("status") or STATUS_SUSPEITA)
        distribuicao[status] = distribuicao.get(status, 0) + 1
    ultimo = historico[0]
    return {
        "fonte": fonte.upper().strip(),
        "ticker": _normalizar_ticker(ticker),
        "quantidade": len(historico),
        "score_medio": round(mean(scores), 2),
        "ultimo_status": ultimo.get("status"),
        "ultimo_score": ultimo.get("score_confianca_fonte"),
        "status_distribuicao": distribuicao,
        "uso": "AUDITORIA_APENAS",
        "altera_decisao_automaticamente": False,
    }
