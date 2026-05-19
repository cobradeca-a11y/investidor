"""
decisao/objeto_decisao.py

Objeto formal de decisão do FIIA.

A decisão não deve ser apenas uma string como COMPRAR/VENDER.
Ela precisa carregar risco, confiança, margem, fontes, gates, justificativas
e gatilhos de invalidação.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
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


CONTRATO_DECISAO_CAMPOS = [
    "ticker",
    "data_analise",
    "decisao",
    "acao",
    "motivo",
    "confianca",
    "risco",
    "score_final",
    "preco_atual",
    "preco_justo",
    "preco_entrada",
    "preco_teto",
    "margem",
    "segmento",
    "gate_parada",
    "trilha_gates",
    "gates_detalhes",
    "penalidades",
    "alertas",
    "dimensionamento",
    "zonas_entrada",
    "confianca_dados",
    "versao_modelo",
    "contexto_versao",
]


def _acao_operacional(decisao: str | None) -> str:
    decisao_norm = (decisao or "MONITORAR").upper().strip()
    mapa = {
        "COMPRAR_PARCIAL": AcaoOperacional.COMPRAR_PARCIALMENTE.value,
        "COMPRAR_PARCIALMENTE": AcaoOperacional.COMPRAR_PARCIALMENTE.value,
        "EVITAR": AcaoOperacional.EVITAR_ENTRADA.value,
        "EVITAR_PRECO": AcaoOperacional.EVITAR_ENTRADA.value,
        "ELIMINADO_LIQUIDEZ": AcaoOperacional.EVITAR_ENTRADA.value,
        "ELIMINADO_TAMANHO": AcaoOperacional.EVITAR_ENTRADA.value,
        "ELIMINADO_RISCO_ESTRUTURAL": AcaoOperacional.EVITAR_ENTRADA.value,
        "ELIMINADO_RENDA_INSUFICIENTE": AcaoOperacional.EVITAR_ENTRADA.value,
        "BLOQUEADO_DADOS_INSUFICIENTES": AcaoOperacional.MONITORAR.value,
        "BLOQUEADO_CONTEXTO_INCOMPLETO": AcaoOperacional.MONITORAR.value,
        "BLOQUEADO_HISTORICO_INSUFICIENTE": AcaoOperacional.MONITORAR.value,
        "BLOQUEADO_PRECO": AcaoOperacional.MONITORAR.value,
        "BLOQUEADO_CONFIABILIDADE_BAIXA": AcaoOperacional.MONITORAR.value,
        "MONITORAR": AcaoOperacional.MONITORAR.value,
        "AGUARDAR": AcaoOperacional.AGUARDAR.value,
        "MANTER": AcaoOperacional.MANTER.value,
        "REDUZIR": AcaoOperacional.REDUZIR.value,
        "VENDER": AcaoOperacional.VENDER.value,
        "COMPRAR": AcaoOperacional.COMPRAR.value,
    }
    return mapa.get(decisao_norm, decisao_norm)


def _risco_operacional(veredito: dict[str, Any]) -> str:
    if veredito.get("risco"):
        return str(veredito.get("risco")).upper()

    decisao = (veredito.get("decisao") or "").upper()
    if decisao.startswith("ELIMINADO") or decisao.startswith("BLOQUEADO"):
        return NivelRisco.ALTO.value
    if veredito.get("alertas") or veredito.get("penalidades"):
        return NivelRisco.MODERADO.value
    return NivelRisco.INDETERMINADO.value


def _confianca_dados(veredito: dict[str, Any]) -> dict[str, Any]:
    dados = veredito.get("confianca_dados")
    if isinstance(dados, dict):
        return dados

    gate55 = veredito.get("gate55_confianca_dados") or {}
    return {
        "score_global": (
            veredito.get("score_confianca_dados_consolidado")
            or veredito.get("score_confianca_dados")
            or gate55.get("score_confianca_dados")
        ),
        "nivel_uso": (
            veredito.get("nivel_uso_dados_consolidado")
            or veredito.get("nivel_uso_dados")
            or gate55.get("nivel_uso_dados")
        ),
    }


def normalizar_contrato_decisao(veredito: dict[str, Any], contexto: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Garante o contrato final de decisao consumido por API, PWA, persistencia
    e backtesting sem alterar a decisao calculada pelo motor.
    """
    payload = dict(veredito or {})
    contexto = contexto or {}

    decisao = payload.get("decisao") or payload.get("status") or "MONITORAR"
    ticker = (payload.get("ticker") or contexto.get("ticker") or "").upper().replace(".SA", "").strip()
    gates = payload.get("gates_detalhes") or {}

    payload.setdefault("ticker", ticker)
    payload.setdefault("data_analise", date.today().isoformat())
    payload.setdefault("decisao", decisao)
    payload.setdefault("acao", _acao_operacional(decisao))
    payload.setdefault("motivo", payload.get("status") or "Decisao gerada pelo motor FIIA.")
    payload.setdefault("confianca", "INDETERMINADA")
    payload.setdefault("risco", _risco_operacional(payload))
    payload.setdefault("score_final", payload.get("score_ia"))
    payload.setdefault("preco_atual", payload.get("preco") or contexto.get("preco"))
    payload.setdefault("preco_justo", contexto.get("preco_justo"))
    payload.setdefault("preco_entrada", payload.get("preco_teto"))
    payload.setdefault("preco_teto", payload.get("preco_entrada"))
    payload.setdefault("margem", payload.get("margem_seguranca"))
    payload.setdefault("segmento", contexto.get("segmento"))
    payload.setdefault("gate_parada", None)
    payload.setdefault("trilha_gates", [f"Gate {gate}: {dados.get('status')}" for gate, dados in sorted(gates.items())])
    payload.setdefault("gates_detalhes", gates)
    payload.setdefault("penalidades", [])
    payload.setdefault("alertas", [])
    payload.setdefault("dimensionamento", None)
    payload.setdefault("zonas_entrada", None)
    payload.setdefault("confianca_dados", _confianca_dados(payload))
    payload.setdefault("versao_modelo", "2.1")
    payload.setdefault("contexto_versao", contexto.get("contexto_versao"))

    return payload


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
    preco_entrada: float | None = None
    preco_teto: float | None = None
    decisao: str | None = None
    motivo: str | None = None
    segmento: str | None = None
    gate_parada: int | None = None
    trilha_gates: list[str] = field(default_factory=list)
    gates_detalhes: dict[str, Any] = field(default_factory=dict)
    penalidades: list[str] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)
    dimensionamento: dict[str, Any] | None = None
    zonas_entrada: dict[str, Any] | None = None
    confianca_dados: dict[str, Any] = field(default_factory=dict)
    contexto_versao: str | None = None
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
        payload = {
            "ticker": self.ticker,
            "data_analise": self.criado_em[:10],
            "decisao": self.decisao or self.acao.value,
            "acao": self.acao.value,
            "motivo": self.motivo or "; ".join(self.justificativas),
            "risco": self.risco.value,
            "confianca": self.confianca.value,
            "score_final": self.score_final,
            "margem_seguranca": self.margem_seguranca,
            "margem": self.margem_seguranca,
            "preco_atual": self.preco_atual,
            "preco_justo": self.preco_justo,
            "preco_entrada": self.preco_entrada,
            "preco_teto": self.preco_teto,
            "segmento": self.segmento,
            "gate_parada": self.gate_parada,
            "trilha_gates": self.trilha_gates,
            "gates_detalhes": self.gates_detalhes,
            "penalidades": self.penalidades,
            "alertas": self.alertas,
            "dimensionamento": self.dimensionamento,
            "zonas_entrada": self.zonas_entrada,
            "confianca_dados": self.confianca_dados,
            "justificativas": self.justificativas,
            "riscos": self.riscos,
            "gatilhos_invalidez": self.gatilhos_invalidez,
            "gates": [gate.to_dict() for gate in self.gates],
            "fontes": [fonte.to_dict() for fonte in self.fontes],
            "contexto": self.contexto,
            "versao_modelo": self.versao_modelo,
            "contexto_versao": self.contexto_versao or self.contexto.get("contexto_versao"),
            "criado_em": self.criado_em,
        }
        return normalizar_contrato_decisao(payload, self.contexto)


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
