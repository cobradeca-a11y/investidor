"""
coleta/cvm_informe_mensal.py

Conector CVM — Informes Mensais de FIIs.

Objetivo:
- trazer CVM para o núcleo estrutural do FIIA;
- persistir VP/cota, patrimônio líquido, cotistas e competência;
- permitir recalcular P/VP internamente;
- reduzir dependência de Fundamentus para dados patrimoniais.

Observação:
Os ZIPs públicos da CVM não exigem token CKAN.
"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from banco import db
from sistema import observabilidade

BASE_URL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_{ano}.zip"
TABELA = "cvm_informes_mensais_fii"

_MAPEAMENTO_COLUNAS = {
    "cnpj_fundo": ["CNPJ_FUNDO", "CNPJ_FUNDO_CLASSE", "CNPJ", "CNPJ_FII"],
    "competencia": ["DT_COMPTC", "DT_REFER", "DATA_REFERENCIA", "COMPETENCIA"],
    "patrimonio_liquido": ["VL_PATRIM_LIQ", "VL_PATRIMONIO_LIQUIDO", "PATRIMONIO_LIQUIDO"],
    "valor_patrimonial_cota": ["VL_PATRIM_COTA", "VL_QUOTA", "VL_COTA", "VALOR_PATRIMONIAL_COTA"],
    "num_cotistas": ["NR_COTST", "NR_COTISTAS", "NUM_COTISTAS"],
    "num_cotas": ["QT_COTAS", "QT_COTA", "QUANTIDADE_COTAS"],
}


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def garantir_tabela() -> None:
    sql = f"""
    CREATE TABLE IF NOT EXISTS {TABELA} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cnpj_fundo TEXT NOT NULL,
        competencia TEXT NOT NULL,
        patrimonio_liquido REAL,
        valor_patrimonial_cota REAL,
        num_cotistas INTEGER,
        num_cotas REAL,
        fonte TEXT NOT NULL DEFAULT 'CVM_INF_MENSAL',
        ano INTEGER,
        arquivo_origem TEXT,
        coletado_em TEXT NOT NULL,
        payload_json TEXT,
        UNIQUE(cnpj_fundo, competencia)
    );
    """
    db.executar(sql)


def _baixar_zip(ano: int) -> bytes:
    url = BASE_URL.format(ano=ano)
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def _normalizar_nome_coluna(nome: str) -> str:
    return str(nome).strip().upper()


def _localizar_coluna(df: pd.DataFrame, candidatos: list[str]) -> str | None:
    colunas = {_normalizar_nome_coluna(c): c for c in df.columns}
    for candidato in candidatos:
        chave = _normalizar_nome_coluna(candidato)
        if chave in colunas:
            return colunas[chave]
    return None


def _to_float(valor: Any) -> float | None:
    if valor is None or pd.isna(valor):
        return None
    try:
        if isinstance(valor, str):
            valor = valor.replace(".", "").replace(",", ".")
        return float(valor)
    except Exception:
        return None


def _to_int(valor: Any) -> int | None:
    numero = _to_float(valor)
    return int(numero) if numero is not None else None


def _ler_csv_do_zip(conteudo_zip: bytes) -> list[tuple[str, pd.DataFrame]]:
    arquivos: list[tuple[str, pd.DataFrame]] = []
    with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as zf:
        for nome in zf.namelist():
            if not nome.lower().endswith((".csv", ".txt")):
                continue
            with zf.open(nome) as arquivo:
                try:
                    df = pd.read_csv(arquivo, sep=";", encoding="latin1", dtype=str)
                except Exception:
                    arquivo.seek(0)
                    df = pd.read_csv(arquivo, sep=";", encoding="utf-8", dtype=str)
                arquivos.append((nome, df))
    return arquivos


def _extrair_registros(ano: int, nome_arquivo: str, df: pd.DataFrame) -> list[dict[str, Any]]:
    colunas = {
        campo: _localizar_coluna(df, candidatos)
        for campo, candidatos in _MAPEAMENTO_COLUNAS.items()
    }

    obrigatorias = ["cnpj_fundo", "competencia"]
    if any(colunas.get(campo) is None for campo in obrigatorias):
        observabilidade.registrar_evento(
            "WARNING",
            "coleta.cvm_informe_mensal",
            "Arquivo ignorado por ausência de colunas obrigatórias",
            fonte="CVM",
            contexto={"arquivo": nome_arquivo, "colunas": list(df.columns)},
        )
        return []

    registros: list[dict[str, Any]] = []
    coletado_em = _agora_iso()

    for _, row in df.iterrows():
        cnpj = row.get(colunas["cnpj_fundo"])
        competencia = row.get(colunas["competencia"])

        if not cnpj or not competencia:
            continue

        registro = {
            "cnpj_fundo": str(cnpj).strip(),
            "competencia": str(competencia).strip()[:10],
            "patrimonio_liquido": _to_float(row.get(colunas["patrimonio_liquido"])) if colunas.get("patrimonio_liquido") else None,
            "valor_patrimonial_cota": _to_float(row.get(colunas["valor_patrimonial_cota"])) if colunas.get("valor_patrimonial_cota") else None,
            "num_cotistas": _to_int(row.get(colunas["num_cotistas"])) if colunas.get("num_cotistas") else None,
            "num_cotas": _to_float(row.get(colunas["num_cotas"])) if colunas.get("num_cotas") else None,
            "fonte": "CVM_INF_MENSAL",
            "ano": ano,
            "arquivo_origem": nome_arquivo,
            "coletado_em": coletado_em,
            "payload_json": row.to_json(force_ascii=False),
        }
        registros.append(registro)

    return registros


def _salvar_registro(registro: dict[str, Any]) -> None:
    colunas = ", ".join(registro.keys())
    placeholders = ", ".join("?" for _ in registro)
    updates = ", ".join(
        f"{col}=excluded.{col}"
        for col in registro.keys()
        if col not in {"cnpj_fundo", "competencia"}
    )
    sql = f"""
    INSERT INTO {TABELA} ({colunas})
    VALUES ({placeholders})
    ON CONFLICT(cnpj_fundo, competencia)
    DO UPDATE SET {updates}
    """
    db.executar(sql, tuple(registro.values()))


def coletar_ano(ano: int) -> dict[str, Any]:
    """Baixa e persiste informes mensais de FIIs de um ano."""
    garantir_tabela()

    try:
        conteudo = _baixar_zip(ano)
        arquivos = _ler_csv_do_zip(conteudo)

        total = 0
        for nome_arquivo, df in arquivos:
            registros = _extrair_registros(ano, nome_arquivo, df)
            for registro in registros:
                _salvar_registro(registro)
            total += len(registros)

        resumo = {"ano": ano, "arquivos": len(arquivos), "registros": total}
        observabilidade.registrar_evento(
            "INFO",
            "coleta.cvm_informe_mensal",
            "Coleta anual concluída",
            fonte="CVM",
            contexto=resumo,
        )
        return resumo

    except Exception as erro:
        observabilidade.registrar_erro(
            "coleta.cvm_informe_mensal",
            erro,
            fonte="CVM",
            contexto={"ano": ano},
        )
        return {"ano": ano, "erro": str(erro), "registros": 0}


def coletar_anos(anos: list[int]) -> list[dict[str, Any]]:
    return [coletar_ano(ano) for ano in anos]


def ultimo_por_cnpj(cnpj_fundo: str) -> dict[str, Any] | None:
    garantir_tabela()
    row = db.buscar_um(
        f"""
        SELECT * FROM {TABELA}
        WHERE cnpj_fundo = ?
        ORDER BY competencia DESC
        LIMIT 1
        """,
        (cnpj_fundo,),
    )
    return dict(row) if row else None
