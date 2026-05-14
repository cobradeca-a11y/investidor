"""
decisao/objeto_decisao.py

Objeto formal de decisão do FIIA.

A decisão não deve ser apenas uma string como COMPRAR/VENDER.
Ela precisa carregar risco, confiança, margem, fontes, gates, justificativas
e gatilhos de invalidação.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AcaoOperacional(str, Enum):
    COMPRAR = "COMPRAR"
    COMPRAR_PARCIALMENTE = "COMPRAR_PARCIALMENTE"
    AGUARDAR = "AGUARDAR"
    MONITORAR = "MONITORAR"
    MANTER = "MANTER"
    REDUZIR = "REDUZIR"
    VENDER = "VENDER"
    EVITAR_ENTRADA = "EVITAR_ENTRADA"


class NivelRisco(str, Enum):
    BAIXO = "BAIXO"
    MODERADO = "MODERADO"
    ALTO = "ALTO"
    CRITICO = "CRITICO"
    INDETERMINADO = "INDETERMINADO"


class NivelConfianca(str, Enum):
    BAIXA = "BAIXA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"
    INDETERMINADA = "INDETERMINADA"


@dataclass
class GateResultado:
    nome: str
    status: str
    motivo: str = ""
    score: float | None = None
    dados_usados: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FonteUsada:
    nome: str
    tipo: str
    confiabilidade: float | None = None
    observacao: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DecisaoFIIA:
    ticker: str
    acao: AcaoOperacional
    risco: NivelRisco = NivelRisco.INDETERMINADO
    confianca: NivelConfianca = NivelConfianca.INDETERMINADA
    score_final: float | None = None
    margem_seguranca: float | None = None
    preco_atual: float | None = None
    preco_justo: float | None = None
    preco_teto: float | None = None
    justificativas: list[str] = field(default_factory=list)
    riscos: list[str] = field(default_factory=list)
    gatilhos_invalidez: list[str] = field(default_factory=list)
    gates: list[GateResultado] = field(default_factory=list)
    fontes: list[FonteUsada] = field(default_factory=list)
    contexto: dict[str, Any] = field(default_factory=dict)
    versao_modelo: str = "fiia-decisao-v1"
    criado_em: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def adicionar_justificativa(self, texto: str) -> None:
        if texto:
            self.justificativas.append(texto)

    def adicionar_risco(self, texto: str) -> None:
        if texto:
            self.riscos.append(texto)

    def adicionar_gatilho(self, texto: str) -> None:
        if texto:
            self.gatilhos_invalidez.append(texto)

    def adicionar_gate(self, gate: GateResultado) -> None:
        self.gates.append(gate)

    def adicionar_fonte(self, fonte: FonteUsada) -> None:
        self.fontes.append(fonte)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "acao": self.acao.value,
            "risco": self.risco.value,
            "confianca": self.confianca.value,
            "score_final": self.score_final,
            "margem_seguranca": self.margem_seguranca,
            "preco_atual": self.preco_atual,
            "preco_justo": self.preco_justo,
            "preco_teto": self.preco_teto,
            "justificativas": self.justificativas,
            "riscos": self.riscos,
            "gatilhos_invalidez": self.gatilhos_invalidez,
            "gates": [gate.to_dict() for gate in self.gates],
            "fontes": [fonte.to_dict() for fonte in self.fontes],
            "contexto": self.contexto,
            "versao_modelo": self.versao_modelo,
            "criado_em": self.criado_em,
        }


def decisao_de_erro(ticker: str, mensagem: str) -> DecisaoFIIA:
    """Cria decisão segura quando a análise não é confiável."""
    decisao = DecisaoFIIA(
        ticker=ticker.upper(),
        acao=AcaoOperacional.MONITORAR,
        risco=NivelRisco.INDETERMINADO,
        confianca=NivelConfianca.BAIXA,
    )
    decisao.adicionar_risco("Análise incompleta ou indisponível.")
    decisao.adicionar_justificativa(mensagem)
    decisao.adicionar_gatilho("Reexecutar análise quando as fontes críticas estiverem disponíveis.")
    return decisao
