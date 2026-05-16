"""
coleta/cvm_fnet_documentos.py

Camada inicial FNET/CVM para documentos de FIIs.

Objetivo:
- persistir metadados de documentos FNET por CNPJ/ticker;
- permitir auditoria de cobertura documental;
- preparar a migração institucional para fatos relevantes, informes e comunicados;
- não substituir ainda o coletor patrimonial de informe mensal.

Observação operacional:
Este módulo aceita importação local CSV/Excel/JSON exportada de fonte FNET/CVM.
A automação de download direto deve ser adicionada quando o formato/fonte final for estabilizado.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from banco import db
from sistema import observabilidade

TABELA = "cvm_fnet_documentos_fii"

_ALIASES = {
    "ticker": ["ticker", "codigo", "código", "cod_negociacao", "codigo_negociacao"],
    "cnpj_fundo": ["cnpj_fundo", "cnpj", "CNPJ_Fundo", "CNPJ FUNDO", "cnpjEmissor"],
    "cnpj_classe": ["cnpj_classe", "CNPJ_Classe", "CNPJ CLASSE"],
    "categoria": ["categoria", "categoria_documento", "tipo", "tipo_documento", "categoriaDocumento"],
    "tipo_documento": ["tipo_documento", "tipo", "especie", "assunto", "descricao"],
    "data_referencia": ["data_referencia", "dt_refer", "dataReferencia", "data_ref", "DT_REFER"],
    "data_entrega": ["data_entrega", "dt_entrega", "dataEntrega", "DT_ENTREGA"],
    "url_documento": ["url_documento", "url", "link", "download", "urlDownload"],
    "protocolo": ["protocolo", "numero_protocolo", "id", "idDocumento"],
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


def garantir_tabela() -> None:
    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            cnpj_fundo TEXT,
            cnpj_classe TEXT,
            categoria TEXT,
            tipo_documento TEXT,
            data_referencia TEXT,
            data_entrega TEXT,
            url_documento TEXT,
            protocolo TEXT,
            assunto TEXT,
            fonte TEXT NOT NULL DEFAULT 'CVM_FNET',
            arquivo_origem TEXT,
            coletado_em TEXT NOT NULL,
            payload_json TEXT,
            dedupe_key TEXT
        );
        """
    )
    _garantir_coluna(TABELA, "dedupe_key", "TEXT")
    db.executar(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{TABELA}_dedupe_key ON {TABELA}(dedupe_key)")


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


def _dedupe_key(dados: dict[str, Any]) -> str:
    """
    Gera chave determinística para deduplicar documentos FNET.

    O protocolo pode vir nulo. Por isso a chave usa COALESCE lógico
    com string vazia e acrescenta outros campos estáveis do documento.
    """
    partes = [
        dados.get("cnpj_fundo") or "",
        dados.get("protocolo") or "",
        dados.get("data_entrega") or "",
        dados.get("data_referencia") or "",
        dados.get("tipo_documento") or "",
        dados.get("categoria") or "",
        dados.get("assunto") or "",
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


def importar_arquivo(caminho_arquivo: str | Path) -> dict[str, Any]:
    """Importa metadados FNET a partir de arquivo local estruturado."""
    garantir_tabela()
    caminho = Path(caminho_arquivo)

    try:
        df = _ler_arquivo(caminho)
        colunas = {campo: _localizar(df, campo) for campo in _ALIASES}

        if not colunas.get("cnpj_fundo") and not colunas.get("ticker"):
            raise ValueError("Arquivo FNET sem CNPJ nem ticker identificável.")

        total = 0
        ignorados = 0
        coletado_em = _agora_iso()

        for _, row in df.iterrows():
            cnpj = _limpar(row.get(colunas["cnpj_fundo"])) if colunas.get("cnpj_fundo") else None
            ticker = _limpar_ticker(row.get(colunas["ticker"])) if colunas.get("ticker") else None
            if not cnpj and not ticker:
                ignorados += 1
                continue

            dados = {
                "ticker": ticker,
                "cnpj_fundo": cnpj,
                "cnpj_classe": _limpar(row.get(colunas["cnpj_classe"])) if colunas.get("cnpj_classe") else None,
                "categoria": _limpar(row.get(colunas["categoria"])) if colunas.get("categoria") else None,
                "tipo_documento": _limpar(row.get(colunas["tipo_documento"])) if colunas.get("tipo_documento") else None,
                "data_referencia": _limpar(row.get(colunas["data_referencia"])) if colunas.get("data_referencia") else None,
                "data_entrega": _limpar(row.get(colunas["data_entrega"])) if colunas.get("data_entrega") else None,
                "url_documento": _limpar(row.get(colunas["url_documento"])) if colunas.get("url_documento") else None,
                "protocolo": _limpar(row.get(colunas["protocolo"])) if colunas.get("protocolo") else None,
                "assunto": _limpar(row.get(colunas["assunto"])) if colunas.get("assunto") else None,
                "fonte": "CVM_FNET",
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
            sql = f"""
            INSERT INTO {TABELA} ({colunas_sql})
            VALUES ({placeholders})
            ON CONFLICT(dedupe_key)
            DO UPDATE SET {updates}
            """
            db.executar(sql, tuple(dados.values()))
            total += 1

        resumo = {"arquivo": str(caminho), "registros": total, "ignorados": ignorados}
        observabilidade.registrar_evento(
            "INFO",
            "coleta.cvm_fnet_documentos",
            "Metadados FNET importados",
            fonte="CVM_FNET",
            contexto=resumo,
        )
        return resumo

    except Exception as erro:
        observabilidade.registrar_erro(
            "coleta.cvm_fnet_documentos",
            erro,
            fonte="CVM_FNET",
            contexto={"arquivo": str(caminho)},
        )
        return {"arquivo": str(caminho), "erro": str(erro), "registros": 0}


def listar_por_ticker(ticker: str, limite: int = 50) -> list[dict[str, Any]]:
    garantir_tabela()
    ticker_norm = ticker.upper().replace(".SA", "")
    rows = db.buscar_todos(
        f"""
        SELECT * FROM {TABELA}
        WHERE ticker = ?
        ORDER BY COALESCE(data_entrega, data_referencia) DESC
        LIMIT ?
        """,
        (ticker_norm, limite),
    )
    return [dict(row) for row in rows]


def listar_por_cnpj(cnpj_fundo: str, limite: int = 50) -> list[dict[str, Any]]:
    garantir_tabela()
    rows = db.buscar_todos(
        f"""
        SELECT * FROM {TABELA}
        WHERE cnpj_fundo = ?
        ORDER BY COALESCE(data_entrega, data_referencia) DESC
        LIMIT ?
        """,
        (cnpj_fundo, limite),
    )
    return [dict(row) for row in rows]


def ultimo_documento_por_cnpj(cnpj_fundo: str) -> dict[str, Any] | None:
    docs = listar_por_cnpj(cnpj_fundo, limite=1)
    return docs[0] if docs else None
