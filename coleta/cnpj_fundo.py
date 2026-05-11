"""
coleta/cnpj_fundo.py
Coleta e persiste o CNPJ de FIIs a partir do Informe Mensal da CVM.

Fonte: https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/
Arquivo: inf_mensal_fii_{ANO}.zip
Arquivo interno: inf_mensal_fii_geral_{ANO}.csv

O ticker e extraido do codigo ISIN:
  BRHGLGCTF004 -> HGLG -> HGLG11
"""

import io
import csv
import re
import zipfile
import requests
from datetime import date
import banco.db as db

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_TIMEOUT  = 45
_BASE_URL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS"

_cache: dict[str, str] = {}


def _ticker_do_isin(isin: str) -> str | None:
    match = re.match(r'BR([A-Z0-9]{4,6})CTF', isin.upper())
    if not match:
        return None
    return match.group(1) + "11"


def _parsear_csv(conteudo: str) -> dict[str, str]:
    mapa = {}
    seen = set()
    for row in csv.DictReader(io.StringIO(conteudo), delimiter=';'):
        isin = row.get('Codigo_ISIN', '').strip()
        cnpj = row.get('CNPJ_Fundo_Classe', '').strip()
        if not isin or not cnpj:
            continue
        ticker = _ticker_do_isin(isin)
        if ticker and ticker not in seen:
            mapa[ticker] = cnpj
            seen.add(ticker)
    return mapa


def _carregar_informe(ano: int) -> dict[str, str]:
    """Baixa inf_mensal_fii_{ANO}.zip e extrai o CSV geral."""
    url = f"{_BASE_URL}/inf_mensal_fii_{ano}.zip"
    try:
        print(f"[cnpj] Baixando {url}...")
        r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if r.status_code != 200:
            print(f"[cnpj] HTTP {r.status_code} para {ano}")
            return {}

        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            # Lista arquivos disponíveis
            arquivos = z.namelist()
            # Busca o arquivo geral
            geral = next(
                (n for n in arquivos if 'geral' in n.lower() and n.endswith('.csv')),
                None
            )
            if not geral:
                print(f"[cnpj] Arquivo geral não encontrado no ZIP. Disponíveis: {arquivos}")
                return {}

            with z.open(geral) as f:
                conteudo = f.read().decode('latin-1')

        mapa = _parsear_csv(conteudo)
        print(f"[cnpj] Informe {ano} carregado: {len(mapa)} tickers mapeados.")
        return mapa

    except Exception as e:
        print(f"[cnpj] Erro ao processar informe {ano}: {e}")
        return {}


def _carregar_cache() -> dict[str, str]:
    global _cache
    if _cache:
        return _cache
    ano = date.today().year
    mapa = _carregar_informe(ano)
    if not mapa:
        mapa = _carregar_informe(ano - 1)
    _cache = mapa
    return mapa


def obter_cnpj(ticker: str) -> str | None:
    ticker = ticker.upper().strip()
    try:
        row = db.buscar_um("SELECT cnpj FROM fiis WHERE ticker = ?", (ticker,))
        if row and row.get("cnpj"):
            return row["cnpj"]
    except Exception:
        pass
    mapa = _carregar_cache()
    cnpj = mapa.get(ticker)
    if cnpj:
        try:
            db.executar("UPDATE fiis SET cnpj = ? WHERE ticker = ?", (cnpj, ticker))
        except Exception:
            pass
    return cnpj


def popular_cnpjs_banco() -> int:
    try:
        db.executar("ALTER TABLE fiis ADD COLUMN cnpj TEXT")
    except Exception:
        pass

    rows = db.buscar_todos("SELECT ticker FROM fiis WHERE cnpj IS NULL OR cnpj = ''")
    tickers = [r["ticker"] for r in rows]

    if not tickers:
        print("[cnpj] Todos os tickers ja tem CNPJ.")
        return 0

    mapa = _carregar_cache()
    atualizados = 0
    for ticker in tickers:
        cnpj = mapa.get(ticker.upper())
        if cnpj:
            try:
                db.executar("UPDATE fiis SET cnpj = ? WHERE ticker = ?", (cnpj, ticker))
                atualizados += 1
            except Exception:
                pass

    print(f"[cnpj] {atualizados}/{len(tickers)} tickers atualizados.")
    return atualizados
