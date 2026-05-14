"""
validacao/confianca_fonte.py

Camada de confiança por fonte/campo do FIIA.

Objetivo:
- medir qualidade do dado usado;
- priorizar fonte oficial;
- detectar ausência/divergência;
- impedir que dados frágeis pareçam confiáveis;
- preparar validação cruzada profissional.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any


class TipoFonte(str, Enum):
    OFICIAL = "OFICIAL"
    DOCUMENTAL = "DOCUMENTAL"
    MERCADO = "MERCADO"
    AUXILIAR = "AUXILIAR"
    IA = "IA"
    DESCONHECIDA = "DESCONHECIDA"


class StatusCampo(str, Enum):
    OK = "OK"
    AUSENTE = "AUSENTE"
    DIVERGENTE = "DIVERGENTE"
    INCOMPLETO = "INCOMPLETO"
    SUSPEITO = "SUSPEITO"
    NAO_VERIFICADO = "NAO_VERIFICADO"


PESOS_FONTE = {
    TipoFonte.OFICIAL: 1.00,
    TipoFonte.DOCUMENTAL: 0.95,
    TipoFonte.MERCADO: 0.75,
    TipoFonte.AUXILIAR: 0.60,
    TipoFonte.IA: 0.45,
    TipoFonte.DESCONHECIDA: 0.25,
}

PENALIDADES_STATUS = {
    StatusCampo.OK: 0.00,
    StatusCampo.NAO_VERIFICADO: 0.15,
    StatusCampo.INCOMPLETO: 0.30,
    StatusCampo.SUSPEITO: 0.40,
    StatusCampo.DIVERGENTE: 0.55,
    StatusCampo.AUSENTE: 0.80,
}


@dataclass
class ConfiancaCampo:
    campo: str
    fonte: str
    tipo_fonte: TipoFonte
    status: StatusCampo
    valor: Any = None
    score: float = 0.0
    observacao: str = ""

    def to_dict(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["tipo_fonte"] = self.tipo_fonte.value
        dados["status"] = self.status.value
        return dados


@dataclass
class ComparacaoCampo:
    campo: str
    principal: ConfiancaCampo
    comparados: list[ConfiancaCampo]
    divergente: bool
    score_consolidado: float
    observacao: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "campo": self.campo,
            "principal": self.principal.to_dict(),
            "comparados": [item.to_dict() for item in self.comparados],
            "divergente": self.divergente,
            "score_consolidado": self.score_consolidado,
            "observacao": self.observacao,
        }


def calcular_score_confianca(tipo_fonte: TipoFonte, status: StatusCampo) -> float:
    base = PESOS_FONTE.get(tipo_fonte, PESOS_FONTE[TipoFonte.DESCONHECIDA])
    penalidade = PENALIDADES_STATUS.get(status, 0.50)
    return round(max(0.0, min(1.0, base - penalidade)), 4)


def classificar_fonte(nome_fonte: str) -> TipoFonte:
    nome = (nome_fonte or "").lower()

    if nome in {"cvm", "cvm dados abertos", "banco central", "bcb", "sgs"}:
        return TipoFonte.OFICIAL
    if nome in {"b3", "fundos.net", "fnet", "fundosnet"}:
        return TipoFonte.DOCUMENTAL
    if nome in {"yahoo", "yfinance", "brapi", "investing", "fundamentus"}:
        return TipoFonte.MERCADO
    if nome in {"status invest", "funds explorer", "infomoney"}:
        return TipoFonte.AUXILIAR
    if nome in {"gemini", "ia", "llm"}:
        return TipoFonte.IA

    return TipoFonte.DESCONHECIDA


def avaliar_campo(
    campo: str,
    fonte: str,
    valor: Any,
    *,
    status: StatusCampo | None = None,
    observacao: str = "",
) -> ConfiancaCampo:
    tipo = classificar_fonte(fonte)

    if status is None:
        if valor is None or valor == "":
            status = StatusCampo.AUSENTE
        else:
            status = StatusCampo.OK

    score = calcular_score_confianca(tipo, status)

    return ConfiancaCampo(
        campo=campo,
        fonte=fonte,
        tipo_fonte=tipo,
        status=status,
        valor=valor,
        score=score,
        observacao=observacao,
    )


def _valores_divergem(valor_a: Any, valor_b: Any, tolerancia_pct: float) -> bool:
    if valor_a is None or valor_b is None:
        return True

    try:
        a = float(valor_a)
        b = float(valor_b)
        if a == 0 and b == 0:
            return False
        base = max(abs(a), abs(b), 1.0)
        return abs(a - b) / base > tolerancia_pct
    except Exception:
        return str(valor_a).strip().lower() != str(valor_b).strip().lower()


def comparar_campo(
    campo: str,
    principal: ConfiancaCampo,
    comparados: list[ConfiancaCampo],
    *,
    tolerancia_pct: float = 0.02,
) -> ComparacaoCampo:
    divergentes = []

    for item in comparados:
        if _valores_divergem(principal.valor, item.valor, tolerancia_pct):
            divergentes.append(item)

    divergente = bool(divergentes)

    todos = [principal] + comparados
    if todos:
        score_medio = sum(item.score for item in todos) / len(todos)
    else:
        score_medio = 0.0

    if divergente:
        score_medio = max(0.0, score_medio - 0.25)
        observacao = f"Campo {campo} possui divergência entre fontes."
    else:
        observacao = f"Campo {campo} validado sem divergência relevante."

    return ComparacaoCampo(
        campo=campo,
        principal=principal,
        comparados=comparados,
        divergente=divergente,
        score_consolidado=round(score_medio, 4),
        observacao=observacao,
    )


def confianca_global(campos: list[ConfiancaCampo | ComparacaoCampo]) -> float:
    if not campos:
        return 0.0

    scores: list[float] = []
    for item in campos:
        if isinstance(item, ComparacaoCampo):
            scores.append(item.score_consolidado)
        else:
            scores.append(item.score)

    return round(sum(scores) / len(scores), 4)
