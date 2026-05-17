import io
import zipfile
import sqlite3
import requests
import pandas as pd
from datetime import date

DB_PATH = "fiia.db"
HEADERS = {"User-Agent": "FIIA/1.0"}

URL_INF_MENSAL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_{ano}.zip"
URL_INF_TRIMESTRAL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_TRIMESTRAL/DADOS/inf_trimestral_fii_{ano}.zip"
URL_INF_ANUAL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_ANUAL/DADOS/inf_anual_fii_{ano}.zip"
URL_DFIN = "https://dados.cvm.gov.br/dados/FII/DOC/DFIN/DADOS/dfin_fii_{ano}.csv"


def baixar_zip(url):
    print(f"Baixando: {url}")
    r = requests.get(url, headers=HEADERS, timeout=60)
    print("Status:", r.status_code)
    r.raise_for_status()
    return zipfile.ZipFile(io.BytesIO(r.content))


def ler_csv_zip(zf, nome):
    with zf.open(nome) as f:
        return pd.read_csv(f, sep=";", encoding="ISO-8859-1", dtype=str, low_memory=False)


def normalizar_cnpj(valor):
    return "".join(ch for ch in str(valor) if ch.isdigit()).zfill(14)


def cnpjs_master():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("""
        SELECT ticker_b3_11, cnpj_fundo, cnpj_classe
        FROM cadastro_fundos_master
        WHERE cnpj_fundo IS NOT NULL
    """, conn)
    conn.close()

    df["cnpj_fundo_norm"] = df["cnpj_fundo"].apply(normalizar_cnpj)
    return set(df["cnpj_fundo_norm"])


def testar_inf_mensal(ano=2026):
    zf = baixar_zip(URL_INF_MENSAL.format(ano=ano))
    print("Arquivos no ZIP mensal:")
    print(zf.namelist())

    cnpjs = cnpjs_master()
    total = 0

    for nome in zf.namelist():
        if not nome.lower().endswith(".csv"):
            continue

        df = ler_csv_zip(zf, nome)
        print("\nArquivo:", nome)
        print("Linhas:", len(df))
        print("Colunas:", list(df.columns)[:20])

        col_cnpj = next((c for c in df.columns if "CNPJ" in c.upper()), None)
        if not col_cnpj:
            print("Sem CNPJ, ignorado.")
            continue

        df[col_cnpj] = df[col_cnpj].apply(normalizar_cnpj)
        filtrado = df[df[col_cnpj].isin(cnpjs)].copy()

        print("Linhas vinculadas à tabela mestre:", len(filtrado))
        print(filtrado.head(3))

        total += len(filtrado)

    print("\nTOTAL INF_MENSAL FILTRADO:", total)


def testar_inf_trimestral(ano=2026):
    zf = baixar_zip(URL_INF_TRIMESTRAL.format(ano=ano))
    print("Arquivos no ZIP trimestral:")
    print(zf.namelist())

    cnpjs = cnpjs_master()
    total = 0

    for nome in zf.namelist():
        if not nome.lower().endswith(".csv"):
            continue

        df = ler_csv_zip(zf, nome)
        print("\nArquivo:", nome)
        print("Linhas:", len(df))
        print("Colunas:", list(df.columns)[:20])

        col_cnpj = next((c for c in df.columns if "CNPJ" in c.upper()), None)
        if not col_cnpj:
            print("Sem CNPJ, ignorado.")
            continue

        df[col_cnpj] = df[col_cnpj].apply(normalizar_cnpj)
        filtrado = df[df[col_cnpj].isin(cnpjs)].copy()

        print("Linhas vinculadas à tabela mestre:", len(filtrado))
        print(filtrado.head(3))

        total += len(filtrado)

    print("\nTOTAL INF_TRIMESTRAL FILTRADO:", total)


def testar_inf_anual(ano=2025):
    zf = baixar_zip(URL_INF_ANUAL.format(ano=ano))
    print("Arquivos no ZIP anual:")
    print(zf.namelist())

    cnpjs = cnpjs_master()
    total = 0

    for nome in zf.namelist():
        if not nome.lower().endswith(".csv"):
            continue

        df = ler_csv_zip(zf, nome)
        print("\nArquivo:", nome)
        print("Linhas:", len(df))
        print("Colunas:", list(df.columns)[:20])

        col_cnpj = next((c for c in df.columns if "CNPJ" in c.upper()), None)
        if not col_cnpj:
            print("Sem CNPJ, ignorado.")
            continue

        df[col_cnpj] = df[col_cnpj].apply(normalizar_cnpj)
        filtrado = df[df[col_cnpj].isin(cnpjs)].copy()

        print("Linhas vinculadas à tabela mestre:", len(filtrado))
        print(filtrado.head(3))

        total += len(filtrado)

    print("\nTOTAL INF_ANUAL FILTRADO:", total)


def testar_dfin(ano=2026):
    url = URL_DFIN.format(ano=ano)
    print(f"Baixando: {url}")

    df = pd.read_csv(url, sep=";", encoding="ISO-8859-1", dtype=str, low_memory=False)
    print("Linhas DFIN:", len(df))
    print("Colunas:", list(df.columns)[:30])
    print(df.head(5))


if __name__ == "__main__":
    testar_inf_mensal(2026)
    testar_inf_trimestral(2026)
    testar_inf_anual(2025)
    testar_dfin(2026)
