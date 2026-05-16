"""
operacional/saude_fontes.py

Auditoria objetiva da saúde das fontes do FIIA.

Mede os pontos que impedem maturidade operacional:
- ativos sem CVM patrimonial;
- ativos sem FNET;
- ativos usando fallback;
- preços sem timestamp ou desatualizados;
- decisões bloqueadas por confiança;
- snapshots ausentes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from banco import db
from sistema import observabilidade


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scalar(sql: str, params: tuple = ()) -> int:
    row = db.buscar_um(sql, params)
    if not row:
        return 0
    return int(row[0] or 0)


def _listar(sql: str, params: tuple = ()) -> list[str]:
    return [str(r[0]) for r in db.buscar_todos(sql, params)]


def gerar_relatorio_saude_fontes() -> dict[str, Any]:
    total_fiis = _scalar("SELECT COUNT(*) FROM fiis WHERE COALESCE(ativo, 1) = 1")
    if total_fiis == 0:
        total_fiis = _scalar("SELECT COUNT(DISTINCT ticker) FROM indicadores")

    sem_indicadores = _listar(
        """
        SELECT f.ticker
        FROM fiis f
        LEFT JOIN indicadores i ON i.ticker = f.ticker
        WHERE COALESCE(f.ativo, 1) = 1
        GROUP BY f.ticker
        HAVING COUNT(i.id) = 0
        ORDER BY f.ticker
        """
    )

    sem_preco_timestamp = _listar(
        """
        SELECT ticker FROM indicadores
        WHERE id IN (SELECT MAX(id) FROM indicadores GROUP BY ticker)
          AND preco IS NOT NULL
          AND (preco_timestamp IS NULL OR preco_timestamp = '')
        ORDER BY ticker
        """
    )

    preco_desatualizado = _listar(
        """
        SELECT ticker FROM indicadores
        WHERE id IN (SELECT MAX(id) FROM indicadores GROUP BY ticker)
          AND preco_timestamp IS NOT NULL
          AND date(substr(preco_timestamp, 1, 10)) < date('now', '-2 days')
        ORDER BY ticker
        """
    )

    fallback_patrimonial = _listar(
        """
        SELECT DISTINCT ticker
        FROM aprendizado_simulacoes
        WHERE fonte_patrimonial = 'FALLBACK_BANCO_ATUAL'
        ORDER BY ticker
        """
    )

    sem_fnet = _listar(
        """
        SELECT DISTINCT ticker
        FROM aprendizado_simulacoes
        WHERE risco = 'SEM_FNET'
        ORDER BY ticker
        """
    )

    bloqueio_confianca = _listar(
        """
        SELECT DISTINCT ticker
        FROM aprendizado_simulacoes
        WHERE confianca = 'BLOQUEAR_DECISAO_FORTE'
        ORDER BY ticker
        """
    )

    sem_snapshot = _listar(
        """
        SELECT f.ticker
        FROM fiis f
        LEFT JOIN snapshots_indicadores s ON s.ticker = f.ticker
        WHERE COALESCE(f.ativo, 1) = 1
        GROUP BY f.ticker
        HAVING COUNT(s.id) = 0
        ORDER BY f.ticker
        """
    )

    cvm_mensal_total = _scalar("SELECT COUNT(*) FROM cvm_informes_mensais_fii")
    fnet_total = _scalar("SELECT COUNT(*) FROM fnet_dividendos_fii")
    simulacoes_total = _scalar("SELECT COUNT(*) FROM aprendizado_simulacoes")
    snapshots_total = _scalar("SELECT COUNT(*) FROM snapshots_indicadores")

    resumo = {
        "gerado_em": _agora_iso(),
        "total_fiis_ativos": total_fiis,
        "cobertura": {
            "sem_indicadores": len(sem_indicadores),
            "sem_preco_timestamp": len(sem_preco_timestamp),
            "preco_desatualizado_mais_2d": len(preco_desatualizado),
            "fallback_patrimonial": len(fallback_patrimonial),
            "sem_fnet": len(sem_fnet),
            "bloqueio_confianca": len(bloqueio_confianca),
            "sem_snapshot": len(sem_snapshot),
        },
        "volumes": {
            "cvm_informes_mensais_fii": cvm_mensal_total,
            "fnet_dividendos_fii": fnet_total,
            "aprendizado_simulacoes": simulacoes_total,
            "snapshots_indicadores": snapshots_total,
        },
        "tickers": {
            "sem_indicadores": sem_indicadores,
            "sem_preco_timestamp": sem_preco_timestamp,
            "preco_desatualizado_mais_2d": preco_desatualizado,
            "fallback_patrimonial": fallback_patrimonial,
            "sem_fnet": sem_fnet,
            "bloqueio_confianca": bloqueio_confianca,
            "sem_snapshot": sem_snapshot,
        },
    }

    observabilidade.registrar_evento(
        "INFO",
        "operacional.saude_fontes",
        "Relatório de saúde das fontes gerado",
        contexto={"cobertura": resumo["cobertura"], "volumes": resumo["volumes"]},
    )
    return resumo


def gerar_painel_saude_fontes() -> dict[str, Any]:
    """Compatibilidade com chamadas anteriores."""
    return gerar_relatorio_saude_fontes()


def imprimir_resumo() -> None:
    print(json.dumps(gerar_relatorio_saude_fontes(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    imprimir_resumo()
