"""
cadastro/resolver_identidade.py
Resolver institucional de identidade dos FIIs.

Fonte primária:
- cadastro_fundos_master, importada da tabela mestre B3 ↔ CVM.

Objetivo:
- centralizar ticker ↔ CNPJ fundo ↔ CNPJ classe ↔ código CVM;
- evitar que coletores CVM/FNET/ANBIMA implementem heurísticas próprias;
- fornecer diagnóstico de cobertura da base mestre.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from banco import db


@dataclass(frozen=True)
class IdentidadeFII:
    ticker: str
    ticker_base: str | None
    cnpj_fundo: str | None
    cnpj_classe: str | None
    codigo_cvm_fundo: int | None
    codigo_cvm_classe: int | None
    fundo_b3: str | None
    razao_social_b3: str | None
    denominacao_fundo_cvm: str | None
    denominacao_classe_cvm: str | None
    administrador: str | None
    gestor: str | None
    classificacao: str | None
    classe_anbima: str | None
    situacao_fundo: str | None
    situacao_classe: str | None
    match_score: float | None
    confianca: str | None
    fonte: str = "cadastro_fundos_master"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _row_para_identidade(row: Any) -> IdentidadeFII | None:
    if not row:
        return None
    return IdentidadeFII(
        ticker=row["ticker_b3_11"],
        ticker_base=row["ticker_base"],
        cnpj_fundo=row["cnpj_fundo"],
        cnpj_classe=row["cnpj_classe"],
        codigo_cvm_fundo=row["codigo_cvm_fundo"],
        codigo_cvm_classe=row["codigo_cvm_classe"],
        fundo_b3=row["fundo_b3"],
        razao_social_b3=row["razao_social_b3"],
        denominacao_fundo_cvm=row["denominacao_fundo_cvm"],
        denominacao_classe_cvm=row["denominacao_classe_cvm"],
        administrador=row["administrador_fundo"],
        gestor=row["gestor_fundo"],
        classificacao=row["classificacao_classe"],
        classe_anbima=row["cad_fi_classe_anbima"],
        situacao_fundo=row["situacao_fundo_cvm"],
        situacao_classe=row["situacao_classe_cvm"],
        match_score=row["match_score"],
        confianca=row["confianca"],
    )


def resolver_por_ticker(ticker: str) -> IdentidadeFII | None:
    """Resolve identidade institucional a partir de ticker B3."""
    ticker_norm = ticker.strip().upper()
    row = db.buscar_um(
        """
        SELECT *
        FROM cadastro_fundos_master
        WHERE ticker_b3_11 = ? OR ticker_base = ?
        LIMIT 1
        """,
        (ticker_norm, ticker_norm),
    )
    return _row_para_identidade(row)


def resolver_por_cnpj(cnpj: str) -> IdentidadeFII | None:
    """Resolve identidade institucional a partir de CNPJ de fundo ou classe."""
    cnpj_norm = cnpj.strip()
    row = db.buscar_um(
        """
        SELECT *
        FROM cadastro_fundos_master
        WHERE cnpj_fundo = ? OR cnpj_classe = ? OR cad_fi_cnpj = ?
        LIMIT 1
        """,
        (cnpj_norm, cnpj_norm, cnpj_norm),
    )
    return _row_para_identidade(row)


def resolver_por_codigo_cvm(codigo_cvm: int | str) -> IdentidadeFII | None:
    """Resolve identidade institucional a partir de código CVM de fundo ou classe."""
    try:
        codigo = int(codigo_cvm)
    except (TypeError, ValueError):
        return None

    row = db.buscar_um(
        """
        SELECT *
        FROM cadastro_fundos_master
        WHERE codigo_cvm_fundo = ? OR codigo_cvm_classe = ?
        LIMIT 1
        """,
        (codigo, codigo),
    )
    return _row_para_identidade(row)


def listar_tickers(ativos: bool = True) -> list[str]:
    """Lista tickers disponíveis na tabela mestre."""
    sql = """
        SELECT ticker_b3_11
        FROM cadastro_fundos_master
        WHERE ticker_b3_11 IS NOT NULL
        ORDER BY ticker_b3_11
    """
    rows = db.buscar_todos(sql)
    return [row["ticker_b3_11"] for row in rows]


def diagnostico_cobertura() -> dict[str, Any]:
    """Retorna diagnóstico objetivo da tabela mestre."""
    def escalar(sql: str) -> int:
        row = db.buscar_um(sql)
        return int(row[0]) if row else 0

    total = escalar("SELECT COUNT(*) FROM cadastro_fundos_master")
    com_ticker = escalar("SELECT COUNT(*) FROM cadastro_fundos_master WHERE ticker_b3_11 IS NOT NULL")
    com_cnpj_fundo = escalar("SELECT COUNT(*) FROM cadastro_fundos_master WHERE cnpj_fundo IS NOT NULL")
    com_cnpj_classe = escalar("SELECT COUNT(*) FROM cadastro_fundos_master WHERE cnpj_classe IS NOT NULL")
    com_codigo_fundo = escalar("SELECT COUNT(*) FROM cadastro_fundos_master WHERE codigo_cvm_fundo IS NOT NULL")
    com_codigo_classe = escalar("SELECT COUNT(*) FROM cadastro_fundos_master WHERE codigo_cvm_classe IS NOT NULL")
    alta_confianca = escalar("""
        SELECT COUNT(*)
        FROM cadastro_fundos_master
        WHERE UPPER(COALESCE(confianca, '')) IN ('ALTA', 'ALTO', 'HIGH')
           OR COALESCE(match_score, 0) >= 0.90
    """)

    return {
        "tabela": "cadastro_fundos_master",
        "total_registros": total,
        "com_ticker": com_ticker,
        "com_cnpj_fundo": com_cnpj_fundo,
        "com_cnpj_classe": com_cnpj_classe,
        "com_codigo_cvm_fundo": com_codigo_fundo,
        "com_codigo_cvm_classe": com_codigo_classe,
        "alta_confianca": alta_confianca,
        "cobertura_ticker_pct": round((com_ticker / total) * 100, 2) if total else 0,
        "cobertura_cnpj_fundo_pct": round((com_cnpj_fundo / total) * 100, 2) if total else 0,
        "cobertura_cnpj_classe_pct": round((com_cnpj_classe / total) * 100, 2) if total else 0,
    }


def imprimir_diagnostico() -> None:
    diag = diagnostico_cobertura()
    print("\n=== DIAGNÓSTICO DA TABELA MESTRE ===")
    for chave, valor in diag.items():
        print(f"{chave}: {valor}")
