"""
coleta/informe_anual.py
Coletor do Informe Anual de FIIs da CVM.

Persiste todos os CSVs do ZIP anual com rastreabilidade e fornece funções
básicas de consumo para contexto institucional e IA.
"""
from __future__ import annotations

import io
import re
import sqlite3
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from banco import db
from sistema import observabilidade

_BASE_URL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_ANUAL/DADOS/inf_anual_fii_{ano}.zip"
_HEADERS = {"User-Agent": "FIIA/1.0"}
_DB_PATH = Path(__file__).resolve().parent.parent / "fiia.db"

_TABELAS = {
    "ativo_adquirido": "cvm_anual_ativo_adquirido",
    "ativo_transacao": "cvm_anual_ativo_transacao",
    "ativo_valor_contabil": "cvm_anual_ativo_valor_contabil",
    "complemento": "cvm_anual_complemento",
    "diretor_responsavel": "cvm_anual_diretor",
    "distribuicao_cotistas": "cvm_anual_distribuicao_cotistas",
    "experiencia_profissional": "cvm_anual_experiencia",
    "geral": "cvm_anual_geral",
    "prestador_servico": "cvm_anual_prestador",
    "processo": "cvm_anual_processo",
    "processo_semelhante": "cvm_anual_processo_semelhante",
    "representante_cotista": "cvm_anual_representante",
}


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalizar_cnpj(valor: str) -> str:
    return re.sub(r"\D", "", str(valor)).zfill(14)


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(_DB_PATH)


def _cnpjs_alvo() -> set[str]:
    rows = db.buscar_todos(
        """
        SELECT cnpj_fundo, cnpj_classe
        FROM cadastro_fundos_master
        WHERE (cnpj_fundo IS NOT NULL AND cnpj_fundo != '')
           OR (cnpj_classe IS NOT NULL AND cnpj_classe != '')
        """
    )
    cnpjs: set[str] = set()
    for row in rows:
        if row["cnpj_fundo"]:
            cnpjs.add(_normalizar_cnpj(row["cnpj_fundo"]))
        if row["cnpj_classe"]:
            cnpjs.add(_normalizar_cnpj(row["cnpj_classe"]))
    return cnpjs


def _col_cnpj(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        cl = c.lower()
        if "cnpj" in cl and ("fundo" in cl or "classe" in cl):
            return c
    for c in df.columns:
        if "cnpj" in c.lower():
            return c
    return None


def _sufixo(nome_arquivo: str, ano: int) -> str:
    base = nome_arquivo.replace(".csv", "").replace(f"_{ano}", "")
    return base.replace("inf_anual_fii_", "")


def _baixar_zip(ano: int) -> zipfile.ZipFile | None:
    url = _BASE_URL.format(ano=ano)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=60)
        if resp.status_code == 404:
            observabilidade.registrar_evento(
                "WARNING",
                "coleta.informe_anual",
                f"ZIP anual {ano} não disponível (404)",
                fonte="CVM",
                contexto={"url": url},
            )
            return None
        resp.raise_for_status()
        return zipfile.ZipFile(io.BytesIO(resp.content))
    except Exception as erro:
        observabilidade.registrar_erro(
            "coleta.informe_anual",
            erro,
            fonte="CVM",
            contexto={"ano": ano, "url": url},
        )
        return None


def _ler_csv(zf: zipfile.ZipFile, nome: str) -> pd.DataFrame | None:
    try:
        with zf.open(nome) as f:
            return pd.read_csv(f, sep=";", encoding="ISO-8859-1", dtype=str, low_memory=False)
    except Exception as erro:
        observabilidade.registrar_evento(
            "WARNING",
            "coleta.informe_anual",
            f"Erro ao ler {nome}: {erro}",
            fonte="CVM",
        )
        return None


def coletar_ano(ano: int) -> dict[str, Any]:
    cnpjs = _cnpjs_alvo()
    if not cnpjs:
        return {"ano": ano, "erro": "Sem CNPJs na tabela mestre", "total": 0}

    zf = _baixar_zip(ano)
    if not zf:
        return {"ano": ano, "erro": "ZIP não disponível", "total": 0}

    resumo: dict[str, int] = {}
    total = 0
    conn = _conn()

    try:
        for nome_arq in zf.namelist():
            if not nome_arq.endswith(".csv"):
                continue

            sufixo = _sufixo(nome_arq, ano)
            tabela = _TABELAS.get(sufixo)
            if not tabela:
                continue

            df = _ler_csv(zf, nome_arq)
            if df is None or df.empty:
                continue

            col = _col_cnpj(df)
            if col:
                df[col] = df[col].fillna("").str.replace(r"\D", "", regex=True).str.zfill(14)
                df = df[df[col].isin(cnpjs)]

            if df.empty:
                continue

            df["ano_referencia"] = ano
            df["coletado_em"] = _agora_iso()
            df.to_sql(tabela, conn, if_exists="append", index=False)
            resumo[tabela] = len(df)
            total += len(df)

        conn.commit()
    finally:
        conn.close()

    observabilidade.registrar_evento(
        "INFO",
        "coleta.informe_anual",
        f"Informe anual {ano} coletado",
        fonte="CVM",
        contexto={"ano": ano, "total": total, "tabelas": resumo},
    )
    return {"ano": ano, "total": total, "tabelas": resumo}


def coletar_anos(anos: list[int]) -> list[dict[str, Any]]:
    return [coletar_ano(ano) for ano in anos]


def coletar_atual() -> dict[str, Any]:
    return coletar_ano(date.today().year - 1)


def processos_por_ticker(ticker: str) -> list[dict]:
    row = db.buscar_um(
        "SELECT cnpj_fundo FROM cadastro_fundos_master WHERE ticker_b3_11 = ?",
        (ticker.upper(),),
    )
    if not row:
        return []
    cnpj = _normalizar_cnpj(row["cnpj_fundo"])
    rows = db.buscar_todos(
        """
        SELECT Numero_Processo, Chance_Perda, Valor_Causa,
               Principais_Fatos, Analise_Impacto_Perda, Data_Referencia
        FROM cvm_anual_processo
        WHERE REPLACE(REPLACE(REPLACE(CNPJ_Fundo_Classe,'.',''),'/',''),'-','') = ?
        ORDER BY Data_Referencia DESC
        """,
        (cnpj,),
    )
    return [dict(r) for r in rows]


def distribuicao_cotistas(ticker: str) -> dict | None:
    row = db.buscar_um(
        "SELECT cnpj_fundo FROM cadastro_fundos_master WHERE ticker_b3_11 = ?",
        (ticker.upper(),),
    )
    if not row:
        return None
    cnpj = _normalizar_cnpj(row["cnpj_fundo"])
    r = db.buscar_um(
        """
        SELECT * FROM cvm_anual_distribuicao_cotistas
        WHERE REPLACE(REPLACE(REPLACE(CNPJ_Fundo_Classe,'.',''),'/',''),'-','') = ?
        ORDER BY Data_Referencia DESC LIMIT 1
        """,
        (cnpj,),
    )
    return dict(r) if r else None


def contexto_anual(ticker: str) -> str:
    processos = processos_por_ticker(ticker)
    dist = distribuicao_cotistas(ticker)

    if not processos and not dist:
        return ""

    linhas = [f"\nDADOS ANUAIS OFICIAIS (CVM) — {ticker}", "─" * 50]

    if processos:
        alto_risco = [p for p in processos if (p.get("Chance_Perda") or "").upper() == "PROVÁVEL"]
        linhas.append(
            f"Processos judiciais: {len(processos)} total"
            + (f" | {len(alto_risco)} com chance PROVÁVEL" if alto_risco else "")
        )

    if dist:
        pf = dist.get("Percentual_Cotas_Detidas_Faixa_Ate_5")
        if pf:
            linhas.append(f"Cotistas com até 5 cotas: {float(pf) * 100:.1f}% das cotas")

    return "\n".join(linhas)
