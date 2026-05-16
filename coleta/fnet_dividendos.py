"""
coleta/fnet_dividendos.py
Coletor/normalizador de rendimentos via FNET — Avisos aos Cotistas.

Objetivo:
- tornar FNET/CVM a fonte primária de dividendos quando houver metadado/documento disponível;
- manter yfinance apenas como fallback;
- persistir valor, data-base, data-com e data-pagamento com fonte rastreável.

Este módulo aceita importação de arquivo local estruturado exportado/extraído do FNET.
A extração automática de PDF fica em camada posterior de NLP/ETL documental.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from banco import db
from processamento.dividendo_recorrente import classificar_dividendos
from sistema import observabilidade

TABELA = "fnet_dividendos_fii"

_ALIASES = {
    "ticker": ["ticker", "codigo", "código", "cod_negociacao", "codigo_negociacao", "ativo"],
    "cnpj_fundo": ["cnpj_fundo", "cnpj", "CNPJ_Fundo", "CNPJ FUNDO", "cnpjEmissor"],
    "data_base": ["data_base", "dt_base", "Data Base"],
    "data_com": ["data_com", "dt_com", "Data COM"],
    "data_pagamento": ["data_pagamento", "dt_pagamento", "pagamento", "data_pgto", "Data Pagamento"],
    "valor": ["valor", "valor_por_cota", "rendimento", "rendimento_por_cota", "valor_provento", "Valor por Cota"],
    "tipo": ["tipo", "tipo_provento", "categoria", "tipo_documento"],
    "protocolo": ["protocolo", "numero_protocolo", "id", "idDocumento"],
    "url_documento": ["url_documento", "url", "link", "download", "urlDownload"],
    "assunto": ["assunto", "titulo", "descricao", "nome_documento"],
}


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_get(row: Any, chave: str, padrao: Any = None) -> Any:
    try:
        return row[chave]
    except Exception:
        return padrao


def _garantir_coluna(nome_tabela: str, nome_coluna: str, definicao: str) -> None:
    colunas = db.buscar_todos(f"PRAGMA table_info({nome_tabela})")
    existentes = {_row_get(col, "name") for col in colunas}
    if nome_coluna not in existentes:
        db.executar(f"ALTER TABLE {nome_tabela} ADD COLUMN {nome_coluna} {definicao}")


def garantir_tabelas() -> None:
    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            cnpj_fundo TEXT,
            data_base TEXT,
            data_com TEXT,
            data_pagamento TEXT NOT NULL,
            valor REAL NOT NULL,
            tipo TEXT DEFAULT 'INDEFINIDO',
            fonte TEXT NOT NULL DEFAULT 'FNET_AVISO_COTISTAS',
            protocolo TEXT,
            url_documento TEXT,
            assunto TEXT,
            arquivo_origem TEXT,
            coletado_em TEXT NOT NULL,
            payload_json TEXT,
            dedupe_key TEXT
        );
        """
    )
    _garantir_coluna(TABELA, "dedupe_key", "TEXT")
    db.executar(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{TABELA}_dedupe_key ON {TABELA}(dedupe_key)")

    _garantir_coluna("dividendos", "data_base", "TEXT")
    _garantir_coluna("dividendos", "data_com", "TEXT")
    _garantir_coluna("dividendos", "protocolo", "TEXT")
    _garantir_coluna("dividendos", "url_documento", "TEXT")


def _norm_coluna(nome: str) -> str:
    return str(nome).strip().lower()


def _localizar(df: pd.DataFrame, campo: str) -> str | None:
    mapa = {_norm_coluna(c): c for c in df.columns}
    for alias in _ALIASES[campo]:
        chave = _norm_coluna(alias)
        if chave in mapa:
            return mapa[chave]
    return None


def _limpar(valor: Any) -> str | None:
    if valor is None or pd.isna(valor):
        return None
    texto = str(valor).strip()
    return texto if texto else None


def _limpar_ticker(valor: Any) -> str | None:
    texto = _limpar(valor)
    return texto.upper().replace(".SA", "") if texto else None


def _normalizar_data(valor: Any) -> str | None:
    texto = _limpar(valor)
    if not texto:
        return None
    try:
        data = pd.to_datetime(texto, dayfirst=True, errors="coerce")
        if pd.isna(data):
            return None
        return data.strftime("%Y-%m-%d")
    except Exception:
        return None


def _normalizar_float(valor: Any) -> float | None:
    texto = _limpar(valor)
    if not texto:
        return None
    texto = re.sub(r"[^0-9,.-]", "", texto)
    if texto.count(",") == 1 and texto.rfind(",") > texto.rfind("."):
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except Exception:
        return None


def _dedupe_key(dados: dict[str, Any]) -> str:
    partes = [
        dados.get("ticker") or "",
        dados.get("cnpj_fundo") or "",
        dados.get("data_pagamento") or "",
        dados.get("data_base") or "",
        dados.get("data_com") or "",
        str(dados.get("valor") or ""),
        dados.get("protocolo") or "",
        dados.get("url_documento") or "",
    ]
    base = "|".join(str(parte).strip().lower() for parte in partes)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _ler_arquivo(caminho: Path) -> pd.DataFrame:
    if caminho.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(caminho, dtype=str)
    if caminho.suffix.lower() == ".json":
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return pd.DataFrame(dados if isinstance(dados, list) else dados.get("dados", []))
    try:
        return pd.read_csv(caminho, sep=None, engine="python", dtype=str, encoding="utf-8")
    except Exception:
        return pd.read_csv(caminho, sep=None, engine="python", dtype=str, encoding="latin1")


def _salvar_operacional(dados: dict[str, Any]) -> None:
    """Grava na tabela dividendos, sobrescrevendo fallback yfinance quando houver FNET."""
    if not dados.get("data_pagamento"):
        raise ValueError("data_pagamento é obrigatório para gravação operacional em dividendos.")

    db.executar(
        """
        DELETE FROM dividendos
        WHERE ticker = ?
          AND data_pagamento = ?
          AND ABS(valor - ?) < 0.000001
          AND COALESCE(fonte, '') <> 'FNET_AVISO_COTISTAS'
        """,
        (dados["ticker"], dados["data_pagamento"], dados["valor"]),
    )

    registro = {
        "ticker": dados["ticker"],
        "data_pagamento": dados["data_pagamento"],
        "valor": dados["valor"],
        "tipo": dados.get("tipo") or "INDEFINIDO",
        "fonte": "FNET_AVISO_COTISTAS",
        "data_base": dados.get("data_base"),
        "data_com": dados.get("data_com"),
        "protocolo": dados.get("protocolo"),
        "url_documento": dados.get("url_documento"),
    }
    db.upsert("dividendos", registro)


def importar_arquivo(caminho_arquivo: str | Path) -> dict[str, Any]:
    """Importa rendimentos de avisos aos cotistas a partir de CSV/Excel/JSON."""
    garantir_tabelas()
    caminho = Path(caminho_arquivo)

    try:
        df = _ler_arquivo(caminho)
        colunas = {campo: _localizar(df, campo) for campo in _ALIASES}

        if not colunas.get("ticker"):
            raise ValueError("Arquivo de dividendos FNET sem coluna de ticker identificável.")
        if not colunas.get("valor"):
            raise ValueError("Arquivo de dividendos FNET sem coluna de valor identificável.")

        total = 0
        ignorados = 0
        ignorados_sem_data_pagamento = 0
        coletado_em = _agora_iso()

        for _, row in df.iterrows():
            ticker = _limpar_ticker(row.get(colunas["ticker"])) if colunas.get("ticker") else None
            valor = _normalizar_float(row.get(colunas["valor"])) if colunas.get("valor") else None
            data_pagamento = _normalizar_data(row.get(colunas["data_pagamento"])) if colunas.get("data_pagamento") else None

            if not data_pagamento:
                ignorados += 1
                ignorados_sem_data_pagamento += 1
                continue
            if not ticker or valor is None:
                ignorados += 1
                continue

            dados = {
                "ticker": ticker,
                "cnpj_fundo": _limpar(row.get(colunas["cnpj_fundo"])) if colunas.get("cnpj_fundo") else None,
                "data_base": _normalizar_data(row.get(colunas["data_base"])) if colunas.get("data_base") else None,
                "data_com": _normalizar_data(row.get(colunas["data_com"])) if colunas.get("data_com") else None,
                "data_pagamento": data_pagamento,
                "valor": valor,
                "tipo": _limpar(row.get(colunas["tipo"])) if colunas.get("tipo") else "INDEFINIDO",
                "fonte": "FNET_AVISO_COTISTAS",
                "protocolo": _limpar(row.get(colunas["protocolo"])) if colunas.get("protocolo") else None,
                "url_documento": _limpar(row.get(colunas["url_documento"])) if colunas.get("url_documento") else None,
                "assunto": _limpar(row.get(colunas["assunto"])) if colunas.get("assunto") else None,
                "arquivo_origem": str(caminho),
                "coletado_em": coletado_em,
                "payload_json": row.to_json(force_ascii=False),
            }
            dados["dedupe_key"] = _dedupe_key(dados)

            colunas_sql = ", ".join(dados.keys())
            placeholders = ", ".join("?" for _ in dados)
            updates = ", ".join(
                f"{col}=excluded.{col}"
                for col in dados
                if col not in {"dedupe_key"}
            )
            db.executar(
                f"""
                INSERT INTO {TABELA} ({colunas_sql})
                VALUES ({placeholders})
                ON CONFLICT(dedupe_key)
                DO UPDATE SET {updates}
                """,
                tuple(dados.values()),
            )
            _salvar_operacional(dados)
            total += 1

        tickers = sorted({str(t).upper().replace(".SA", "") for t in df[colunas["ticker"]].dropna()}) if colunas.get("ticker") else []
        for ticker in tickers:
            classificar_dividendos(ticker)

        resumo = {
            "arquivo": str(caminho),
            "registros": total,
            "ignorados": ignorados,
            "ignorados_sem_data_pagamento": ignorados_sem_data_pagamento,
            "tickers": tickers,
        }
        observabilidade.registrar_evento(
            "INFO",
            "coleta.fnet_dividendos",
            "Dividendos FNET importados como fonte primária",
            fonte="FNET_AVISO_COTISTAS",
            contexto=resumo,
        )
        return resumo

    except Exception as erro:
        observabilidade.registrar_erro(
            "coleta.fnet_dividendos",
            erro,
            fonte="FNET_AVISO_COTISTAS",
            contexto={"arquivo": str(caminho)},
        )
        return {"arquivo": str(caminho), "erro": str(erro), "registros": 0}


def cobertura_fnet(ticker: str) -> dict[str, Any]:
    garantir_tabelas()
    ticker_norm = ticker.upper().replace(".SA", "")
    row = db.buscar_um(
        """
        SELECT COUNT(*) AS qtd, MIN(data_pagamento) AS inicio, MAX(data_pagamento) AS fim
        FROM dividendos
        WHERE ticker = ? AND fonte = 'FNET_AVISO_COTISTAS'
        """,
        (ticker_norm,),
    )
    return {
        "ticker": ticker_norm,
        "fonte_primaria": "FNET_AVISO_COTISTAS",
        "qtd": int(row["qtd"] or 0) if row else 0,
        "inicio": row["inicio"] if row else None,
        "fim": row["fim"] if row else None,
        "tem_fnet": bool(row and row["qtd"]),
    }
