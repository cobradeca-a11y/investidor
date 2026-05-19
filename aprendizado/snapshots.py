"""
aprendizado/snapshots.py
Snapshots históricos diários para replay futuro sem look-ahead bias.

Neste ciclo, os snapshots são gravados e consultáveis e podem ser usados pelo
backtest institucional quando houver snapshot histórico suficiente na data de
referência.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any

from banco import db
from sistema import observabilidade

TABELA = "snapshots_indicadores"
VERSAO_SNAPSHOT_BACKTEST = "snapshot-backtest-v1"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(valor: str | date | datetime) -> str:
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)[:10]


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


def _carregar_payload_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(row.get("payload_json") or "{}")
    except Exception:
        return {}


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
        "snapshot_versao": VERSAO_SNAPSHOT_BACKTEST,
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


def buscar_snapshot_historico(
    ticker: str,
    data_referencia: str | date,
    *,
    max_defasagem_dias: int = 45,
) -> dict[str, Any]:
    """
    Busca o snapshot mais recente em ou antes da data de referência.

    Retorna validade institucional explícita. Se não houver snapshot, payload
    inválido ou defasagem excessiva, a validade fica False.
    """
    garantir_tabela()
    ticker_norm = ticker.upper().replace(".SA", "").strip()
    data_ref = _iso(data_referencia)
    row = db.buscar_um(
        f"""
        SELECT * FROM {TABELA}
        WHERE ticker = ? AND data_snapshot <= ?
        ORDER BY data_snapshot DESC, criado_em DESC
        LIMIT 1
        """,
        (ticker_norm, data_ref),
    )
    if not row:
        return {
            "ticker": ticker_norm,
            "data_referencia": data_ref,
            "snapshot_usado": None,
            "validade_institucional": False,
            "motivo_validade": "Sem snapshot histórico em ou antes da data de referência.",
            "payload": None,
        }

    registro = dict(row)
    payload = _carregar_payload_snapshot(registro)
    if not payload:
        return {
            "ticker": ticker_norm,
            "data_referencia": data_ref,
            "snapshot_usado": registro.get("data_snapshot"),
            "hash_snapshot": registro.get("hash_snapshot"),
            "validade_institucional": False,
            "motivo_validade": "Snapshot histórico encontrado, mas payload_json está inválido ou vazio.",
            "payload": None,
        }

    try:
        dt_ref = datetime.strptime(data_ref, "%Y-%m-%d").date()
        dt_snapshot = datetime.strptime(str(registro.get("data_snapshot"))[:10], "%Y-%m-%d").date()
        defasagem = (dt_ref - dt_snapshot).days
    except Exception:
        defasagem = max_defasagem_dias + 1

    validade = defasagem <= max_defasagem_dias
    return {
        "ticker": ticker_norm,
        "data_referencia": data_ref,
        "snapshot_usado": registro.get("data_snapshot"),
        "hash_snapshot": registro.get("hash_snapshot"),
        "origem_snapshot": registro.get("origem_snapshot"),
        "defasagem_dias": defasagem,
        "validade_institucional": validade,
        "motivo_validade": "Snapshot histórico suficiente para a data de referência." if validade else "Snapshot histórico encontrado, mas defasado para uso institucional.",
        "payload": payload,
    }


def contexto_decisao_de_snapshot(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """
    Converte payload de snapshot em contexto histórico para o motor.

    Não coleta dados novos. Se campos mínimos não existirem, retorna None para
    impedir contaminação com dados atuais.
    """
    payload = snapshot.get("payload") if snapshot else None
    if not isinstance(payload, dict):
        return None

    ind = payload.get("indicadores") or {}
    fii = payload.get("fii") or {}
    data_snapshot = snapshot.get("snapshot_usado") or ind.get("data")

    preco = ind.get("preco")
    vpa = ind.get("vpa")
    pvp = ind.get("pvp")
    patrimonio = ind.get("patrimonio_liquido")
    liquidez = ind.get("liquidez_diaria")

    campos_ausentes = []
    for nome, valor in {
        "preco": preco,
        "vpa": vpa,
        "pvp": pvp,
        "patrimonio_liquido": patrimonio,
        "liquidez_diaria": liquidez,
    }.items():
        if valor is None:
            campos_ausentes.append(nome)

    if campos_ausentes:
        return None

    contexto = {
        "contexto_versao": payload.get("contexto_versao") or "snapshot-historico-v1",
        "ticker": snapshot.get("ticker") or payload.get("ticker"),
        "data": str(data_snapshot)[:10],
        "data_referencia": snapshot.get("data_referencia"),
        "snapshot_usado": snapshot.get("snapshot_usado"),
        "hash_snapshot": snapshot.get("hash_snapshot"),
        "segmento": fii.get("segmento") or ind.get("segmento") or "INDEFINIDO",
        "preco": float(preco),
        "preco_atual": float(preco),
        "vpa": float(vpa),
        "pvp": float(pvp),
        "patrimonio_liquido": float(patrimonio),
        "liquidez_diaria": float(liquidez),
        "ultimo_dividendo": float(ind.get("ultimo_dividendo") or 0.0),
        "dy_12m": float(ind.get("dy_12m") or 0.0),
        "dy_recorrente": float(ind.get("dy_12m") or 0.0),
        "recorrencia_dividendos_pct": float(ind.get("recorrencia_dividendos_pct") or 0.0),
        "meses_historico": int(ind.get("meses_historico") or 0),
        "quedas_consecutivas": int(ind.get("quedas_consecutivas") or 0),
        "score_confianca": float(ind.get("score_confianca") or ind.get("confiabilidade") or 70.0),
        "cdi_atual": float(ind.get("cdi_atual") or 0.0),
        "selic_atual": float(ind.get("selic_atual") or 0.0),
        "ipca_atual": float(ind.get("ipca_atual") or 0.0),
        "semaforo_macro": ind.get("semaforo_macro") if isinstance(ind.get("semaforo_macro"), dict) else {},
        "teto_macro": ind.get("teto_macro") or "NEUTRO",
        "premio_cdi": float(ind.get("premio_cdi") or 0.0),
        "patrimonio_fonte": ind.get("patrimonio_fonte") or ind.get("fonte") or "SNAPSHOT_HISTORICO",
        "nivel_uso_dados": ind.get("nivel_uso_dados") or "USAR_COM_CAUTELA",
        "permitir_decisao": True,
        "campos_ausentes": [],
        "campos_vencidos": [],
        "fontes_falharam": [],
    }
    return contexto
