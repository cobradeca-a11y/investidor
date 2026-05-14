"""
servicos/agendador_avaliador.py

Rotina isolada para executar o avaliador temporal do FIIA.

Objetivo:
- permitir agendamento sem acoplar diretamente ao agendador principal;
- rodar avaliações pendentes 90/365 dias;
- registrar observabilidade;
- evitar múltiplas execuções automáticas no mesmo dia;
- preparar aprendizado operacional automático.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aprendizado.avaliador import rodar_avaliacoes_pendentes, taxa_acerto
from banco import db
from sistema import observabilidade

CHAVE_ULTIMA_EXECUCAO = "avaliador_temporal_ultima_execucao"
TABELA_CONTROLE = "sistema_controle_execucao"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _garantir_tabela_controle() -> None:
    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA_CONTROLE} (
            chave TEXT PRIMARY KEY,
            valor TEXT,
            atualizado_em TEXT NOT NULL
        );
        """
    )


def _obter_controle(chave: str) -> str | None:
    _garantir_tabela_controle()
    row = db.buscar_um(
        f"SELECT valor FROM {TABELA_CONTROLE} WHERE chave = ? LIMIT 1",
        (chave,),
    )
    if not row:
        return None
    try:
        return row["valor"]
    except Exception:
        return None


def _salvar_controle(chave: str, valor: str) -> None:
    _garantir_tabela_controle()
    agora = _agora_iso()
    db.executar(
        f"""
        INSERT INTO {TABELA_CONTROLE} (chave, valor, atualizado_em)
        VALUES (?, ?, ?)
        ON CONFLICT(chave) DO UPDATE SET
            valor = excluded.valor,
            atualizado_em = excluded.atualizado_em
        """,
        (chave, valor, agora),
    )


def deve_executar_diariamente(ultima_execucao_iso: str | None) -> bool:
    """Evita múltiplas execuções no mesmo dia."""
    if not ultima_execucao_iso:
        return True

    try:
        ultima = datetime.fromisoformat(ultima_execucao_iso).date()
        hoje = datetime.now(timezone.utc).date()
        return hoje > ultima
    except Exception:
        return True


def executar_avaliador_temporal(forcar: bool = False) -> dict[str, Any]:
    """Executa avaliações temporais pendentes e retorna resumo operacional."""
    inicio = datetime.now(timezone.utc)
    ultima_execucao = _obter_controle(CHAVE_ULTIMA_EXECUCAO)

    if not forcar and not deve_executar_diariamente(ultima_execucao):
        resultado_pulado = {
            "status": "ignorado",
            "motivo": "Avaliador temporal já executado hoje.",
            "ultima_execucao": ultima_execucao,
            "executado_em": inicio.isoformat(),
        }
        observabilidade.registrar_evento(
            "INFO",
            "servicos.agendador_avaliador",
            "Avaliador temporal ignorado por guard diário",
            contexto=resultado_pulado,
        )
        return resultado_pulado

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
            "forcado": forcar,
        }

        _salvar_controle(CHAVE_ULTIMA_EXECUCAO, fim.isoformat())

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


def main() -> None:
    print(executar_avaliador_temporal(forcar=True))


if __name__ == "__main__":
    main()
