"""
validacao/inventario_dependencias.py

Inventário programático das dependências de dados do FIIA.

Objetivo:
- expor quais campos ainda dependem de fontes frágeis;
- priorizar migração para CVM/FNET/BCB;
- servir como base para Gates, auditoria e relatórios técnicos.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any


class Criticidade(str, Enum):
    ALTISSIMA = "ALTISSIMA"
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAIXA = "BAIXA"


class RiscoOperacional(str, Enum):
    ALTO = "ALTO"
    MEDIO = "MEDIO"
    BAIXO = "BAIXO"


class StatusMigracao(str, Enum):
    NUCLEO_OFICIAL = "NUCLEO_OFICIAL"
    PARCIAL = "PARCIAL"
    FONTE_FRAGIL = "FONTE_FRAGIL"
    AUSENTE = "AUSENTE"


@dataclass(frozen=True)
class DependenciaCampo:
    campo: str
    uso: str
    fonte_atual: str
    fallback_oficial: str
    criticidade: Criticidade
    risco_operacional: RiscoOperacional
    status_migracao: StatusMigracao
    acao_recomendada: str

    def to_dict(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["criticidade"] = self.criticidade.value
        dados["risco_operacional"] = self.risco_operacional.value
        dados["status_migracao"] = self.status_migracao.value
        return dados


DEPENDENCIAS: list[DependenciaCampo] = [
    DependenciaCampo(
        campo="ticker",
        uso="identidade do ativo",
        fonte_atual="base local/Fundamentus/Yahoo",
        fallback_oficial="B3 + CVM/FNET",
        criticidade=Criticidade.ALTA,
        risco_operacional=RiscoOperacional.MEDIO,
        status_migracao=StatusMigracao.PARCIAL,
        acao_recomendada="consolidar tabela mestre B3/CVM como fonte obrigatória",
    ),
    DependenciaCampo(
        campo="cnpj_fundo",
        uso="identidade canônica",
        fonte_atual="CVM/tabela mestre em progresso",
        fallback_oficial="CVM",
        criticidade=Criticidade.ALTISSIMA,
        risco_operacional=RiscoOperacional.MEDIO,
        status_migracao=StatusMigracao.PARCIAL,
        acao_recomendada="tornar obrigatório no pipeline de análise",
    ),
    DependenciaCampo(
        campo="cnpj_classe",
        uso="identidade canônica",
        fonte_atual="CVM em progresso",
        fallback_oficial="CVM",
        criticidade=Criticidade.ALTISSIMA,
        risco_operacional=RiscoOperacional.MEDIO,
        status_migracao=StatusMigracao.PARCIAL,
        acao_recomendada="normalizar em tabela própria",
    ),
    DependenciaCampo(
        campo="preco",
        uso="Gate 0, Gate 4, margem de segurança",
        fonte_atual="Fundamentus/Yahoo",
        fallback_oficial="B3/brapi/Yahoo como mercado com timestamp",
        criticidade=Criticidade.ALTA,
        risco_operacional=RiscoOperacional.MEDIO,
        status_migracao=StatusMigracao.PARCIAL,
        acao_recomendada="manter como dado de mercado, mas exigir timestamp e fonte",
    ),
    DependenciaCampo(
        campo="liquidez_diaria",
        uso="Gate 1",
        fonte_atual="Fundamentus",
        fallback_oficial="B3/brapi/Yahoo com média própria",
        criticidade=Criticidade.ALTA,
        risco_operacional=RiscoOperacional.ALTO,
        status_migracao=StatusMigracao.FONTE_FRAGIL,
        acao_recomendada="calcular média própria de volume/liquidez via histórico de mercado",
    ),
    DependenciaCampo(
        campo="pvp",
        uso="Gate 0, Gate 4",
        fonte_atual="Fundamentus",
        fallback_oficial="CVM VP/cota + preço de mercado",
        criticidade=Criticidade.ALTA,
        risco_operacional=RiscoOperacional.ALTO,
        status_migracao=StatusMigracao.FONTE_FRAGIL,
        acao_recomendada="recalcular internamente",
    ),
    DependenciaCampo(
        campo="vpa",
        uso="Gate 0, margem de segurança",
        fonte_atual="Fundamentus",
        fallback_oficial="CVM informe mensal",
        criticidade=Criticidade.ALTISSIMA,
        risco_operacional=RiscoOperacional.ALTO,
        status_migracao=StatusMigracao.FONTE_FRAGIL,
        acao_recomendada="CVM deve virar fonte primária",
    ),
    DependenciaCampo(
        campo="patrimonio_liquido",
        uso="Gate 1, saúde patrimonial",
        fonte_atual="Fundamentus",
        fallback_oficial="CVM informe mensal/trimestral",
        criticidade=Criticidade.ALTA,
        risco_operacional=RiscoOperacional.ALTO,
        status_migracao=StatusMigracao.FONTE_FRAGIL,
        acao_recomendada="migrar para CVM",
    ),
    DependenciaCampo(
        campo="dy_12m",
        uso="Gate 0, Gate 3, renda",
        fonte_atual="Fundamentus/Yahoo",
        fallback_oficial="rendimentos próprios + preço de mercado",
        criticidade=Criticidade.ALTA,
        risco_operacional=RiscoOperacional.ALTO,
        status_migracao=StatusMigracao.FONTE_FRAGIL,
        acao_recomendada="recalcular internamente com base de rendimentos versionada",
    ),
    DependenciaCampo(
        campo="dividendos",
        uso="Gate 3, avaliador temporal, renda",
        fonte_atual="Yahoo",
        fallback_oficial="FNET/documentos + base própria",
        criticidade=Criticidade.ALTA,
        risco_operacional=RiscoOperacional.ALTO,
        status_migracao=StatusMigracao.FONTE_FRAGIL,
        acao_recomendada="criar histórico próprio versionado e validar com FNET",
    ),
    DependenciaCampo(
        campo="vacancia_fisica",
        uso="Gate 2",
        fonte_atual="Fundamentus/CVM trimestral parcial",
        fallback_oficial="CVM informe trimestral/relatórios FNET",
        criticidade=Criticidade.ALTA,
        risco_operacional=RiscoOperacional.MEDIO,
        status_migracao=StatusMigracao.PARCIAL,
        acao_recomendada="priorizar CVM trimestral e relatórios gerenciais",
    ),
    DependenciaCampo(
        campo="segmento",
        uso="Gates, contexto setorial, ranking",
        fonte_atual="base local/Fundamentus",
        fallback_oficial="classificação própria + validação documental",
        criticidade=Criticidade.ALTA,
        risco_operacional=RiscoOperacional.MEDIO,
        status_migracao=StatusMigracao.PARCIAL,
        acao_recomendada="criar taxonomia interna versionada",
    ),
    DependenciaCampo(
        campo="taxas_gestao_administracao",
        uso="governança",
        fonte_atual="ausente/parcial",
        fallback_oficial="regulamento/FNET/informe anual",
        criticidade=Criticidade.MEDIA,
        risco_operacional=RiscoOperacional.ALTO,
        status_migracao=StatusMigracao.AUSENTE,
        acao_recomendada="extrair de regulamento e informe anual",
    ),
    DependenciaCampo(
        campo="politica_distribuicao",
        uso="qualidade da renda",
        fonte_atual="ausente/parcial",
        fallback_oficial="regulamento/FNET/informe anual",
        criticidade=Criticidade.ALTA,
        risco_operacional=RiscoOperacional.ALTO,
        status_migracao=StatusMigracao.AUSENTE,
        acao_recomendada="extrair e versionar política de distribuição",
    ),
]


def listar_dependencias() -> list[dict[str, Any]]:
    return [item.to_dict() for item in DEPENDENCIAS]


def listar_dependencias_criticas() -> list[dict[str, Any]]:
    return [
        item.to_dict()
        for item in DEPENDENCIAS
        if item.criticidade in {Criticidade.ALTISSIMA, Criticidade.ALTA}
    ]


def listar_fontes_frageis() -> list[dict[str, Any]]:
    return [
        item.to_dict()
        for item in DEPENDENCIAS
        if item.status_migracao in {StatusMigracao.FONTE_FRAGIL, StatusMigracao.AUSENTE}
    ]


def resumo_dependencias() -> dict[str, Any]:
    total = len(DEPENDENCIAS)
    por_status: dict[str, int] = {}
    por_risco: dict[str, int] = {}
    por_criticidade: dict[str, int] = {}

    for item in DEPENDENCIAS:
        por_status[item.status_migracao.value] = por_status.get(item.status_migracao.value, 0) + 1
        por_risco[item.risco_operacional.value] = por_risco.get(item.risco_operacional.value, 0) + 1
        por_criticidade[item.criticidade.value] = por_criticidade.get(item.criticidade.value, 0) + 1

    return {
        "total_campos_mapeados": total,
        "por_status_migracao": por_status,
        "por_risco_operacional": por_risco,
        "por_criticidade": por_criticidade,
        "campos_criticos": [item.campo for item in DEPENDENCIAS if item.criticidade in {Criticidade.ALTISSIMA, Criticidade.ALTA}],
        "campos_em_fonte_fragil": [item.campo for item in DEPENDENCIAS if item.status_migracao == StatusMigracao.FONTE_FRAGIL],
        "campos_ausentes": [item.campo for item in DEPENDENCIAS if item.status_migracao == StatusMigracao.AUSENTE],
    }


def risco_campo(campo: str) -> dict[str, Any] | None:
    campo_normalizado = campo.strip().lower()
    for item in DEPENDENCIAS:
        if item.campo.lower() == campo_normalizado:
            return item.to_dict()
    return None
