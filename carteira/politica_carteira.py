"""
carteira/politica_carteira.py

Política de gestão de carteira do FIIA.

Objetivo:
- transformar decisões de ativo em condução de carteira;
- controlar concentração por ativo e segmento;
- respeitar confiança dos dados e origem patrimonial;
- sugerir tamanho de posição sem depender ainda de tabela de carteira.

Este módulo NÃO calcula IR e NÃO persiste posições.
A carteira no banco virá depois, no Passo 4.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Any


class AcaoCarteira(str, Enum):
    APORTAR = "APORTAR"
    APORTAR_PARCIAL = "APORTAR_PARCIAL"
    MANTER = "MANTER"
    REDUZIR = "REDUZIR"
    VENDER = "VENDER"
    AGUARDAR = "AGUARDAR"
    BLOQUEAR_APORTE = "BLOQUEAR_APORTE"


class MetodoPrecoMedio(str, Enum):
    CUSTO_MEDIO_PONDERADO = "CUSTO_MEDIO_PONDERADO"


@dataclass(frozen=True)
class LimitesCarteira:
    max_por_ativo_pct: float = 0.10
    max_por_segmento_pct: float = 0.30
    caixa_minimo_pct: float = 0.05
    max_ativo_fallback_pct: float = 0.04
    max_ativo_gate55_penalizado_pct: float = 0.05
    aporte_base_pct: float = 0.03
    aporte_parcial_pct: float = 0.015
    metodo_preco_medio: MetodoPrecoMedio = MetodoPrecoMedio.CUSTO_MEDIO_PONDERADO

    def to_dict(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["metodo_preco_medio"] = self.metodo_preco_medio.value
        return dados


@dataclass
class ResultadoPoliticaCarteira:
    ticker: str
    acao_carteira: AcaoCarteira
    percentual_sugerido: float
    metodo_preco_medio: MetodoPrecoMedio
    motivos: list[str] = field(default_factory=list)
    travas: list[str] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)
    limites: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["acao_carteira"] = self.acao_carteira.value
        dados["metodo_preco_medio"] = self.metodo_preco_medio.value
        return dados


def _norm(texto: str | None) -> str:
    return (texto or "").upper().strip()


def _adicionar_trava(travas: list[str], texto: str) -> None:
    if texto and texto not in travas:
        travas.append(texto)


def _adicionar_alerta(alertas: list[str], texto: str) -> None:
    if texto and texto not in alertas:
        alertas.append(texto)


def avaliar_alocacao_sugerida(
    *,
    ticker: str,
    decisao: str,
    risco: str | None = None,
    confianca: str | None = None,
    segmento: str | None = None,
    fonte_patrimonial: str | None = None,
    gate55_status: str | None = None,
    percentual_atual_ativo: float = 0.0,
    percentual_atual_segmento: float = 0.0,
    caixa_disponivel_pct: float = 1.0,
    limites: LimitesCarteira | None = None,
) -> ResultadoPoliticaCarteira:
    """
    Transforma uma decisão do motor em ação de carteira.

    Percentuais esperados em escala decimal:
    - 0.10 = 10%
    - 0.03 = 3%
    """
    limites = limites or LimitesCarteira()
    ticker_norm = ticker.upper().replace(".SA", "").strip()
    decisao_norm = _norm(decisao)
    risco_norm = _norm(risco)
    confianca_norm = _norm(confianca)
    gate55_norm = _norm(gate55_status)
    fonte_norm = _norm(fonte_patrimonial)

    motivos: list[str] = []
    travas: list[str] = []
    alertas: list[str] = []

    motivos.append(f"Decisão recebida do motor: {decisao_norm or 'INDEFINIDA'}.")

    if caixa_disponivel_pct <= limites.caixa_minimo_pct:
        _adicionar_trava(
            travas,
            f"Caixa disponível ({caixa_disponivel_pct:.1%}) está no limite mínimo ({limites.caixa_minimo_pct:.1%}).",
        )

    if percentual_atual_ativo >= limites.max_por_ativo_pct:
        _adicionar_trava(
            travas,
            f"Ativo já atingiu o limite máximo por ativo ({limites.max_por_ativo_pct:.1%}).",
        )

    if percentual_atual_segmento >= limites.max_por_segmento_pct:
        _adicionar_trava(
            travas,
            f"Segmento já atingiu o limite máximo ({limites.max_por_segmento_pct:.1%}).",
        )

    usa_fallback = "FALLBACK" in fonte_norm or fonte_norm in {"FUNDAMENTUS", "BANCO_ATUAL", "FALLBACK_BANCO_ATUAL"}
    if usa_fallback and percentual_atual_ativo >= limites.max_ativo_fallback_pct:
        _adicionar_trava(
            travas,
            f"Ativo com dado patrimonial em fallback não pode passar de {limites.max_ativo_fallback_pct:.1%} da carteira.",
        )
    elif usa_fallback:
        _adicionar_alerta(
            alertas,
            "Dado patrimonial veio de fallback; aporte deve ser conservador.",
        )

    gate_penalizado = gate55_norm in {
        "PENALIZADO_CONFIANCA_DADOS",
        "BLOQUEADO_COMPRA_FORTE_DADOS_FRAGEIS",
        "BLOQUEADO_CONFIANCA_DADOS_INSUFICIENTE",
        "BLOQUEADO_ERRO_CONFIANCA_DADOS",
    }
    if gate_penalizado and percentual_atual_ativo >= limites.max_ativo_gate55_penalizado_pct:
        _adicionar_trava(
            travas,
            f"Gate 5.5 penalizado/bloqueado limita o ativo a {limites.max_ativo_gate55_penalizado_pct:.1%} da carteira.",
        )
    elif gate_penalizado:
        _adicionar_alerta(
            alertas,
            f"Gate 5.5 exige cautela: {gate55_norm}.",
        )

    if risco_norm in {"ALTO", "CRITICO"}:
        _adicionar_alerta(alertas, f"Risco {risco_norm}; posição deve ser reduzida ou limitada.")

    if confianca_norm in {"BAIXA", "INDETERMINADA"}:
        _adicionar_alerta(alertas, f"Confiança {confianca_norm}; evitar aumento agressivo.")

    if decisao_norm in {"VENDER", "EVITAR", "EVITAR_ENTRADA"}:
        return ResultadoPoliticaCarteira(
            ticker=ticker_norm,
            acao_carteira=AcaoCarteira.VENDER if decisao_norm == "VENDER" else AcaoCarteira.BLOQUEAR_APORTE,
            percentual_sugerido=0.0,
            metodo_preco_medio=limites.metodo_preco_medio,
            motivos=motivos + ["Decisão defensiva impede novo aporte."],
            travas=travas,
            alertas=alertas,
            limites=limites.to_dict(),
        )

    if decisao_norm in {"REDUZIR"}:
        return ResultadoPoliticaCarteira(
            ticker=ticker_norm,
            acao_carteira=AcaoCarteira.REDUZIR,
            percentual_sugerido=0.0,
            metodo_preco_medio=limites.metodo_preco_medio,
            motivos=motivos + ["Motor indicou redução de exposição."],
            travas=travas,
            alertas=alertas,
            limites=limites.to_dict(),
        )

    if decisao_norm in {"AGUARDAR", "MONITORAR"}:
        return ResultadoPoliticaCarteira(
            ticker=ticker_norm,
            acao_carteira=AcaoCarteira.AGUARDAR,
            percentual_sugerido=0.0,
            metodo_preco_medio=limites.metodo_preco_medio,
            motivos=motivos + ["Decisão pede acompanhamento, não aporte."],
            travas=travas,
            alertas=alertas,
            limites=limites.to_dict(),
        )

    if travas:
        return ResultadoPoliticaCarteira(
            ticker=ticker_norm,
            acao_carteira=AcaoCarteira.BLOQUEAR_APORTE,
            percentual_sugerido=0.0,
            metodo_preco_medio=limites.metodo_preco_medio,
            motivos=motivos + ["Aporte bloqueado por travas de carteira."],
            travas=travas,
            alertas=alertas,
            limites=limites.to_dict(),
        )

    espaco_ativo = max(0.0, limites.max_por_ativo_pct - percentual_atual_ativo)
    espaco_segmento = max(0.0, limites.max_por_segmento_pct - percentual_atual_segmento)
    caixa_utilizavel = max(0.0, caixa_disponivel_pct - limites.caixa_minimo_pct)

    if decisao_norm == "COMPRAR":
        alvo = limites.aporte_base_pct
        acao = AcaoCarteira.APORTAR
    elif decisao_norm in {"COMPRAR_PARCIAL", "COMPRAR_PARCIALMENTE"}:
        alvo = limites.aporte_parcial_pct
        acao = AcaoCarteira.APORTAR_PARCIAL
    elif decisao_norm == "MANTER":
        alvo = 0.0
        acao = AcaoCarteira.MANTER
    else:
        alvo = 0.0
        acao = AcaoCarteira.AGUARDAR

    if usa_fallback:
        alvo = min(alvo, limites.aporte_parcial_pct)
    if gate_penalizado:
        alvo = min(alvo, limites.aporte_parcial_pct)
    if risco_norm == "ALTO":
        alvo = min(alvo, limites.aporte_parcial_pct)
    if risco_norm == "CRITICO":
        alvo = 0.0
        acao = AcaoCarteira.BLOQUEAR_APORTE
        _adicionar_trava(travas, "Risco crítico bloqueia aumento de posição.")

    percentual_sugerido = min(alvo, espaco_ativo, espaco_segmento, caixa_utilizavel)

    if percentual_sugerido <= 0 and acao in {AcaoCarteira.APORTAR, AcaoCarteira.APORTAR_PARCIAL}:
        acao = AcaoCarteira.BLOQUEAR_APORTE
        motivos.append("Sem espaço disponível por ativo, segmento ou caixa.")

    return ResultadoPoliticaCarteira(
        ticker=ticker_norm,
        acao_carteira=acao,
        percentual_sugerido=round(percentual_sugerido, 4),
        metodo_preco_medio=limites.metodo_preco_medio,
        motivos=motivos,
        travas=travas,
        alertas=alertas,
        limites=limites.to_dict(),
    )


def avaliar_alocacao_por_veredito(
    veredito: dict[str, Any],
    *,
    percentual_atual_ativo: float = 0.0,
    percentual_atual_segmento: float = 0.0,
    caixa_disponivel_pct: float = 1.0,
    segmento: str | None = None,
    limites: LimitesCarteira | None = None,
) -> dict[str, Any]:
    """Atalho para avaliar política de carteira usando o payload de decisão."""
    gate55 = veredito.get("gate55_confianca_dados", {}) or {}
    resultado = avaliar_alocacao_sugerida(
        ticker=veredito.get("ticker", ""),
        decisao=veredito.get("decisao", "MONITORAR"),
        risco=veredito.get("risco"),
        confianca=veredito.get("confianca"),
        segmento=segmento or veredito.get("segmento"),
        fonte_patrimonial=veredito.get("fonte_patrimonial"),
        gate55_status=gate55.get("status"),
        percentual_atual_ativo=percentual_atual_ativo,
        percentual_atual_segmento=percentual_atual_segmento,
        caixa_disponivel_pct=caixa_disponivel_pct,
        limites=limites,
    )
    return resultado.to_dict()
