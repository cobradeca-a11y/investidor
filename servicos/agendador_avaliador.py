"""
servicos/agendador_avaliador.py

Rotina isolada para executar o avaliador temporal do FIIA.

Objetivo:
- permitir agendamento sem acoplar diretamente ao agendador principal;
- rodar avaliações pendentes 90/365 dias;
- registrar observabilidade;
- preparar aprendizado operacional automático.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aprendizado.avaliador import rodar_avaliacoes_pendentes, taxa_acerto
from sistema import observabilidade


def executar_avaliador_temporal() -> dict[str, Any]:
    """Executa avaliações temporais pendentes e retorna resumo operacional."""
    inicio = datetime.now(timezone.utc)

    try:
        resultado = rodar_avaliacoes_pendentes()
        resumo_90 = taxa_acerto(90)
        resumo_365 = taxa_acerto(365)

        fim = datetime.now(timezone.utc)
        duracao_segundos = round((fim - inicio).total_seconds(), 2)

        resumo = {
            "status": "ok",
            "executado_em": fim.isoformat(),
            "duracao_segundos": duracao_segundos,
            "avaliacoes_processadas": resultado,
            "taxa_acerto_90d": resumo_90,
            "taxa_acerto_365d": resumo_365,
        }

        observabilidade.registrar_evento(
            "INFO",
            "servicos.agendador_avaliador",
            "Avaliador temporal executado",
            contexto=resumo,
        )

        return resumo

    except Exception as erro:
        observabilidade.registrar_erro(
            "servicos.agendador_avaliador",
            erro,
        )
        return {
            "status": "erro",
            "executado_em": datetime.now(timezone.utc).isoformat(),
            "erro": str(erro),
        }


def deve_executar_diariamente(ultima_execucao_iso: str | None) -> bool:
    """
    Helper simples para evitar múltiplas execuções no mesmo dia.
    Pode ser usado pelo agendador principal depois.
    """
    if not ultima_execucao_iso:
        return True

    try:
        ultima = datetime.fromisoformat(ultima_execucao_iso).date()
        hoje = datetime.now(timezone.utc).date()
        return hoje > ultima
    except Exception:
        return True
