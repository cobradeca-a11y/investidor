"""
validacao/relatorio_confianca.py

Relatório consolidado de confiança dos dados usados na análise.

Esta camada transforma avaliações campo-a-campo em um diagnóstico simples:
- confiança global;
- campos críticos frágeis;
- divergências;
- recomendação de uso na decisão.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

from validacao.confianca_fonte import ConfiancaCampo, ComparacaoCampo, confianca_global


class NivelUsoDecisao(str, Enum):
    CONFIAVEL = "CONFIAVEL"
    USAR_COM_CAUTELA = "USAR_COM_CAUTELA"
    BLOQUEAR_DECISAO_FORTE = "BLOQUEAR_DECISAO_FORTE"
    INSUFICIENTE = "INSUFICIENTE"


@dataclass
class RelatorioConfianca:
    ticker: str
    score_global: float
    nivel_uso: NivelUsoDecisao
    campos_criticos_frageis: list[str] = field(default_factory=list)
    divergencias: list[str] = field(default_factory=list)
    observacoes: list[str] = field(default_factory=list)
    detalhes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["nivel_uso"] = self.nivel_uso.value
        return dados


def gerar_relatorio_confianca(
    ticker: str,
    campos: list[ConfiancaCampo | ComparacaoCampo],
    *,
    campos_criticos: list[str] | None = None,
) -> RelatorioConfianca:
    """Gera diagnóstico consolidado de confiança para uma análise."""
    campos_criticos = campos_criticos or []
    score = confianca_global(campos)

    campos_frageis: list[str] = []
    divergencias: list[str] = []
    observacoes: list[str] = []
    detalhes: list[dict[str, Any]] = []

    for item in campos:
        item_dict = item.to_dict()
        detalhes.append(item_dict)

        if isinstance(item, ComparacaoCampo):
            if item.divergente:
                divergencias.append(item.campo)
            campo_nome = item.campo
            item_score = item.score_consolidado
        else:
            campo_nome = item.campo
            item_score = item.score

        if campo_nome in campos_criticos and item_score < 0.60:
            campos_frageis.append(campo_nome)

    if score >= 0.80 and not campos_frageis and not divergencias:
        nivel = NivelUsoDecisao.CONFIAVEL
        observacoes.append("Dados suficientes para decisão com boa confiança operacional.")
    elif score >= 0.60 and len(campos_frageis) <= 1:
        nivel = NivelUsoDecisao.USAR_COM_CAUTELA
        observacoes.append("Dados utilizáveis, mas a decisão deve ser conservadora.")
    elif score >= 0.40:
        nivel = NivelUsoDecisao.BLOQUEAR_DECISAO_FORTE
        observacoes.append("Dados frágeis: bloquear compra forte e preferir monitoramento.")
    else:
        nivel = NivelUsoDecisao.INSUFICIENTE
        observacoes.append("Dados insuficientes para decisão operacional confiável.")

    if campos_frageis:
        observacoes.append(f"Campos críticos frágeis: {', '.join(campos_frageis)}.")
    if divergencias:
        observacoes.append(f"Divergências detectadas: {', '.join(divergencias)}.")

    return RelatorioConfianca(
        ticker=ticker.upper(),
        score_global=score,
        nivel_uso=nivel,
        campos_criticos_frageis=campos_frageis,
        divergencias=divergencias,
        observacoes=observacoes,
        detalhes=detalhes,
    )


def aplicar_confianca_na_acao(acao_atual: str, relatorio: RelatorioConfianca) -> str:
    """
    Rebaixa ação operacional quando a confiança dos dados não sustenta decisão forte.
    Não melhora decisão; apenas reduz agressividade.
    """
    acao = (acao_atual or "").upper()

    if relatorio.nivel_uso == NivelUsoDecisao.CONFIAVEL:
        return acao

    if relatorio.nivel_uso == NivelUsoDecisao.USAR_COM_CAUTELA:
        if acao == "COMPRAR":
            return "COMPRAR_PARCIALMENTE"
        return acao

    if relatorio.nivel_uso == NivelUsoDecisao.BLOQUEAR_DECISAO_FORTE:
        if acao in {"COMPRAR", "COMPRAR_PARCIALMENTE"}:
            return "MONITORAR"
        return acao

    if relatorio.nivel_uso == NivelUsoDecisao.INSUFICIENTE:
        return "MONITORAR"

    return acao
