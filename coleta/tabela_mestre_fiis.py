"""
coleta/tabela_mestre_fiis.py

Ingestão da tabela mestre FIIA: ticker B3 -> CNPJ fundo/classe CVM.

Essa tabela é o elo canônico entre:
- radar por ticker;
- informes CVM por CNPJ;
- documentos FNET;
- carteira;
- decisão auditável.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from banco import db
from sistema import observabilidade

TABELA = "fiia_tabela_mestre_fiis"

_ALIASES = {
    "ticker": ["ticker", "ticker_base", "ticker_b3_11", "codigo", "código", "cod_negociacao", "codneg", "Código"],
    "cnpj_fundo": ["cnpj_fundo", "cnpj fundo", "cnpj", "CNPJ_Fundo", "CNPJ FUNDO"],
    "cnpj_classe": ["cnpj_classe", "cnpj classe", "CNPJ_Classe", "CNPJ CLASSE"],
    "razao_social": ["razao_social", "razão social", "razao social", "Razão Social"],
    "nome_fundo": ["fundo", "nome_fundo", "nome fundo", "Fundo"],
}


def garantir_tabela() -> None:
    sql = f"""
    CREATE TABLE IF NOT EXISTS {TABELA} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL UNIQUE,
        cnpj_fundo TEXT,
        cnpj_classe TEXT,
        razao_social TEXT,
        nome_fundo TEXT,
        fonte TEXT NOT NULL DEFAULT 'TABELA_MESTRE_FIIA',
        arquivo_origem TEXT,
        atualizado_em TEXT DEFAULT (datetime('now','localtime'))
    );
    """
    db.executar(sql)


def _norm_coluna(nome: str) -> str:
    return str(nome).strip().lower()


def _localizar(df: pd.DataFrame, campo: str) -> str | None:
    mapa = {_norm_coluna(c): c for c in df.columns}
    for alias in _ALIASES[campo]:
        chave = _norm_coluna(alias)
        if chave in mapa:
            return mapa[chave]
    return None


def _limpar_texto(valor: Any) -> str | None:
    if valor is None or pd.isna(valor):
        return None
    texto = str(valor).strip()
    return texto if texto else None


def _limpar_ticker(valor: Any) -> str | None:
    texto = _limpar_texto(valor)
    if not texto:
        return None
    return texto.upper().replace(".SA", "").strip()


def _ler_csv(caminho: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(caminho, sep=None, engine="python", dtype=str, encoding="utf-8")
    except Exception:
        return pd.read_csv(caminho, sep=None, engine="python", dtype=str, encoding="latin1")


def importar_csv(caminho_csv: str | Path) -> dict[str, Any]:
    """Importa a tabela mestre CSV para SQLite."""
    garantir_tabela()
    caminho = Path(caminho_csv)

    try:
        df = _ler_csv(caminho)
        col_ticker = _localizar(df, "ticker")
        col_cnpj_fundo = _localizar(df, "cnpj_fundo")
        col_cnpj_classe = _localizar(df, "cnpj_classe")
        col_razao = _localizar(df, "razao_social")
        col_nome = _localizar(df, "nome_fundo")

        if not col_ticker:
            raise ValueError(f"Tabela mestre sem coluna de ticker. Colunas: {list(df.columns)}")

        total = 0
        ignorados = 0

        for _, row in df.iterrows():
            ticker = _limpar_ticker(row.get(col_ticker))
            if not ticker:
                ignorados += 1
                continue

            dados = {
                "ticker": ticker,
                "cnpj_fundo": _limpar_texto(row.get(col_cnpj_fundo)) if col_cnpj_fundo else None,
                "cnpj_classe": _limpar_texto(row.get(col_cnpj_classe)) if col_cnpj_classe else None,
                "razao_social": _limpar_texto(row.get(col_razao)) if col_razao else None,
                "nome_fundo": _limpar_texto(row.get(col_nome)) if col_nome else None,
                "fonte": "TABELA_MESTRE_FIIA",
                "arquivo_origem": str(caminho),
            }

            colunas = ", ".join(dados.keys())
            placeholders = ", ".join("?" for _ in dados)
            updates = ", ".join(f"{col}=excluded.{col}" for col in dados if col != "ticker")
            sql = f"""
            INSERT INTO {TABELA} ({colunas})
            VALUES ({placeholders})
            ON CONFLICT(ticker) DO UPDATE SET {updates}
            """
            db.executar(sql, tuple(dados.values()))
            total += 1

        resumo = {"arquivo": str(caminho), "registros": total, "ignorados": ignorados}
        observabilidade.registrar_evento(
            "INFO",
            "coleta.tabela_mestre_fiis",
            "Tabela mestre importada",
            contexto=resumo,
        )
        return resumo

    except Exception as erro:
        observabilidade.registrar_erro(
            "coleta.tabela_mestre_fiis",
            erro,
            contexto={"arquivo": str(caminho)},
        )
        return {"arquivo": str(caminho), "erro": str(erro), "registros": 0}


def obter_por_ticker(ticker: str) -> dict[str, Any] | None:
    garantir_tabela()
    row = db.buscar_um(
        f"SELECT * FROM {TABELA} WHERE ticker = ? LIMIT 1",
        (ticker.upper().replace(".SA", ""),),
    )
    return dict(row) if row else None


def obter_cnpj_fundo(ticker: str) -> str | None:
    item = obter_por_ticker(ticker)
    return item.get("cnpj_fundo") if item else None


def listar_sem_cnpj() -> list[dict[str, Any]]:
    garantir_tabela()
    rows = db.buscar_todos(
        f"""
        SELECT * FROM {TABELA}
        WHERE cnpj_fundo IS NULL OR cnpj_fundo = ''
        ORDER BY ticker
        """
    )
    return [dict(row) for row in rows]
