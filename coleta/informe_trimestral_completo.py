"""
coleta/informe_trimestral_completo.py
Extensão do informe_trimestral.py existente.

Persiste os CSVs trimestrais complementares:
- composição de ativos;
- resultado financeiro;
- contratos;
- inquilinos;
- aquisições;
- alienações;
- desempenho;
- garantias.

Não substitui o módulo original.
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

_BASE_URL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_TRIMESTRAL/DADOS/inf_trimestral_fii_{ano}.zip"
_HEADERS = {"User-Agent": "FIIA/1.0"}
_DB_PATH = Path(__file__).resolve().parent.parent / "fiia.db"

_JA_COBERTOS = {"imovel", "complemento"}

_TABELAS = {
    "alienacao_imovel": "cvm_tri_alienacao_imovel",
    "alienacao_terreno": "cvm_tri_alienacao_terreno",
    "aquisicao_imovel": "cvm_tri_aquisicao_imovel",
    "aquisicao_terreno": "cvm_tri_aquisicao_terreno",
    "ativo": "cvm_tri_ativo",
    "ativo_garantia_rentabilidade": "cvm_tri_ativo_garantia",
    "direito": "cvm_tri_direito",
    "geral": "cvm_tri_geral",
    "imovel_desempenho": "cvm_tri_imovel_desempenho",
    "imovel_renda_acabado_contrato": "cvm_tri_imovel_contrato",
    "imovel_renda_acabado_inquilino": "cvm_tri_imovel_inquilino",
    "rentabilidade_efetiva": "cvm_tri_rentabilidade",
    "resultado_contabil_financeiro": "cvm_tri_resultado",
    "terreno": "cvm_tri_terreno",
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
    return base.replace("inf_trimestral_fii_", "")


def _baixar_zip(ano: int) -> zipfile.ZipFile | None:
    url = _BASE_URL.format(ano=ano)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=60)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return zipfile.ZipFile(io.BytesIO(resp.content))
    except Exception as erro:
        observabilidade.registrar_erro(
            "coleta.informe_trimestral_completo",
            erro,
            fonte="CVM",
            contexto={"ano": ano, "url": url},
        )
        return None


def coletar_ano(ano: int) -> dict[str, Any]:
    cnpjs = _cnpjs_alvo()
    if not cnpjs:
        return {"ano": ano, "erro": "Sem CNPJs na tabela mestre", "total": 0}

    zf = _baixar_zip(ano)
    if not zf:
        return {"ano": ano, "erro": "ZIP não disponível", "total": 0}

    conn = _conn()
    resumo: dict[str, int] = {}
    total = 0

    try:
        for nome_arq in zf.namelist():
            if not nome_arq.endswith(".csv"):
                continue

            sufixo = _sufixo(nome_arq, ano)
            if sufixo in _JA_COBERTOS:
                continue

            tabela = _TABELAS.get(sufixo)
            if not tabela:
                continue

            try:
                with zf.open(nome_arq) as f:
                    df = pd.read_csv(f, sep=";", encoding="ISO-8859-1", dtype=str, low_memory=False)
            except Exception:
                continue

            if df.empty:
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
        "coleta.informe_trimestral_completo",
        f"Trimestral completo {ano} coletado",
        fonte="CVM",
        contexto={"ano": ano, "total": total, "tabelas": resumo},
    )
    return {"ano": ano, "total": total, "tabelas": resumo}


def coletar_atual() -> dict[str, Any]:
    ano = date.today().year
    resultado = coletar_ano(ano)
    if resultado.get("total", 0) == 0:
        resultado = coletar_ano(ano - 1)
    return resultado


def composicao_ativo(ticker: str) -> list[dict]:
    row = db.buscar_um(
        "SELECT cnpj_fundo FROM cadastro_fundos_master WHERE ticker_b3_11 = ?",
        (ticker.upper(),),
    )
    if not row:
        return []
    cnpj = _normalizar_cnpj(row["cnpj_fundo"])
    rows = db.buscar_todos(
        """
        SELECT Tipo, Nome_Ativo, Valor, Quantidade, Data_Referencia
        FROM cvm_tri_ativo
        WHERE REPLACE(REPLACE(REPLACE(CNPJ_Fundo_Classe,'.',''),'/',''),'-','') = ?
        ORDER BY Data_Referencia DESC
        LIMIT 30
        """,
        (cnpj,),
    )
    return [dict(r) for r in rows]


def resultado_financeiro(ticker: str) -> dict | None:
    row = db.buscar_um(
        "SELECT cnpj_fundo FROM cadastro_fundos_master WHERE ticker_b3_11 = ?",
        (ticker.upper(),),
    )
    if not row:
        return None
    cnpj = _normalizar_cnpj(row["cnpj_fundo"])
    r = db.buscar_um(
        """
        SELECT * FROM cvm_tri_resultado
        WHERE REPLACE(REPLACE(REPLACE(CNPJ_Fundo_Classe,'.',''),'/',''),'-','') = ?
        ORDER BY Data_Referencia DESC LIMIT 1
        """,
        (cnpj,),
    )
    return dict(r) if r else None


def inquilinos_principais(ticker: str, top: int = 5) -> list[dict]:
    row = db.buscar_um(
        "SELECT cnpj_fundo FROM cadastro_fundos_master WHERE ticker_b3_11 = ?",
        (ticker.upper(),),
    )
    if not row:
        return []
    cnpj = _normalizar_cnpj(row["cnpj_fundo"])
    rows = db.buscar_todos(
        """
        SELECT Nome_Imovel, Setor_Atuacao,
               CAST(Percentual_Receitas_FII AS REAL) AS pct_receita_fii,
               Data_Referencia
        FROM cvm_tri_imovel_inquilino
        WHERE REPLACE(REPLACE(REPLACE(CNPJ_Fundo_Classe,'.',''),'/',''),'-','') = ?
        ORDER BY pct_receita_fii DESC
        LIMIT ?
        """,
        (cnpj, top),
    )
    return [dict(r) for r in rows]


def contexto_trimestral_completo(ticker: str) -> str:
    composicao = composicao_ativo(ticker)
    resultado = resultado_financeiro(ticker)
    inquilinos = inquilinos_principais(ticker)

    if not composicao and not resultado and not inquilinos:
        return ""

    linhas = [f"\nDETALHE TRIMESTRAL ESTENDIDO (CVM) — {ticker}", "─" * 50]

    if resultado:
        rec_aluguel = resultado.get("Receita_Aluguel_Investimento_Financeiro")
        rend_pagar = resultado.get("Rendimento_Liquido_Pagar")
        if rec_aluguel:
            linhas.append(f"Receita aluguel: R$ {float(rec_aluguel):,.2f}")
        if rend_pagar:
            linhas.append(f"Rendimento líquido pagar: R$ {float(rend_pagar):,.2f}")

    if inquilinos:
        linhas.append("\nPrincipais inquilinos:")
        for inq in inquilinos:
            pct = inq.get("pct_receita_fii")
            setor = inq.get("Setor_Atuacao") or "N/D"
            nome = inq.get("Nome_Imovel") or "N/D"
            pct_str = f"{float(pct) * 100:.1f}%" if pct else "N/D"
            linhas.append(f"  • {nome} | {setor} | {pct_str} da receita FII")

    if composicao:
        tipos = {}
        for ativo in composicao:
            t = ativo.get("Tipo") or "Outro"
            tipos[t] = tipos.get(t, 0) + 1
        linhas.append(f"\nComposição carteira: {dict(tipos)}")

    return "\n".join(linhas)
