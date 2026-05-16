"""
aprendizado/snapshots.py
Snapshots históricos diários para replay futuro sem look-ahead bias.

Neste ciclo, os snapshots são gravados e consultáveis, mas o motor ainda não
executa replay institucional automaticamente.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from banco import db
from sistema import observabilidade

TABELA = "snapshots_indicadores"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def garantir_tabela() -> None:
    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            data_snapshot TEXT NOT NULL,
            origem_snapshot TEXT NOT NULL DEFAULT 'rotina_diaria',
            payload_json TEXT NOT NULL,
            hash_snapshot TEXT NOT NULL,
            criado_em TEXT NOT NULL,
            UNIQUE(ticker, data_snapshot, hash_snapshot)
        );
        """
    )
    db.executar(f"CREATE INDEX IF NOT EXISTS idx_{TABELA}_ticker_data ON {TABELA}(ticker, data_snapshot)")


def _hash_payload(payload: dict[str, Any]) -> str:
    texto = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def criar_snapshot_ticker(ticker: str, origem: str = "rotina_diaria") -> dict[str, Any]:
    garantir_tabela()
    ticker_norm = ticker.upper().replace(".SA", "")
    ind = db.buscar_um(
        "SELECT * FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
        (ticker_norm,),
    )
    fii = db.buscar_um("SELECT * FROM fiis WHERE ticker = ?", (ticker_norm,))
    if not ind:
        return {"ticker": ticker_norm, "status": "sem_indicadores"}

    payload = {
        "ticker": ticker_norm,
        "indicadores": dict(ind),
        "fii": dict(fii) if fii else {},
    }
    data_snapshot = str(ind["data"])
    hash_snapshot = _hash_payload(payload)
    dados = {
        "ticker": ticker_norm,
        "data_snapshot": data_snapshot,
        "origem_snapshot": origem,
        "payload_json": json.dumps(payload, ensure_ascii=False, default=str),
        "hash_snapshot": hash_snapshot,
        "criado_em": _agora_iso(),
    }
    db.executar(
        f"""
        INSERT OR IGNORE INTO {TABELA}
        (ticker, data_snapshot, origem_snapshot, payload_json, hash_snapshot, criado_em)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        tuple(dados.values()),
    )
    return {"ticker": ticker_norm, "data_snapshot": data_snapshot, "hash_snapshot": hash_snapshot, "status": "ok"}


def criar_snapshots_diarios(origem: str = "rotina_diaria") -> dict[str, Any]:
    garantir_tabela()
    rows = db.buscar_todos("SELECT ticker FROM fiis WHERE COALESCE(ativo, 1) = 1 ORDER BY ticker")
    if not rows:
        rows = db.buscar_todos("SELECT DISTINCT ticker FROM indicadores ORDER BY ticker")

    resultados = [criar_snapshot_ticker(row["ticker"], origem=origem) for row in rows]
    ok = sum(1 for r in resultados if r.get("status") == "ok")
    resumo = {"total": len(resultados), "gravados_ou_existentes": ok, "resultados": resultados}
    observabilidade.registrar_evento(
        "INFO",
        "aprendizado.snapshots",
        "Snapshots diários gerados",
        contexto={"total": len(resultados), "ok": ok},
    )
    return resumo


def ultimo_snapshot(ticker: str) -> dict[str, Any] | None:
    garantir_tabela()
    ticker_norm = ticker.upper().replace(".SA", "")
    row = db.buscar_um(
        f"""
        SELECT * FROM {TABELA}
        WHERE ticker = ?
        ORDER BY data_snapshot DESC, criado_em DESC
        LIMIT 1
        """,
        (ticker_norm,),
    )
    return dict(row) if row else None
