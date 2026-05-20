"""
coleta/cnpj_fundo.py
Mapa definitivo ticker->CNPJ usando tabela_mestre_fiia_fiis_b3_cvm.csv
com fallback para informe mensal CVM.

513 FIIs cobertos com confianca Alta.
"""
import io, csv, re, zipfile, requests
from datetime import date
from pathlib import Path
import banco.db as db

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_TIMEOUT  = 30

# CSV da tabela mestre (gerado pelo usuario a partir do cruzamento B3/CVM)
_RAIZ_PROJETO = Path(__file__).resolve().parents[1]
_TABELA_MESTRE_PATH = _RAIZ_PROJETO / "tabela_mestre_fiia_fiis_b3_cvm.csv"

# Fallback: informe mensal CVM
_BASE_CVM = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS"

_cache: dict[str, str] = {}


def _ticker_linha_mestre(row: dict[str, str]) -> str:
    ticker = (row.get("ticker_b3_11") or row.get("ticker") or "").strip().upper()
    if ticker:
        return ticker
    base = (row.get("ticker_base") or "").strip().upper()
    return f"{base}11" if base else ""


def _carregar_tabela_mestre() -> dict[str, str]:
    """Carrega CNPJ da tabela mestre local se existir."""
    for path in [_TABELA_MESTRE_PATH, Path("tabela_mestre_fiia_fiis_b3_cvm.csv")]:
        if not path.exists():
            continue
        mapa = {}
        try:
            with open(path, encoding='utf-8-sig') as f:
                for row in csv.DictReader(f, delimiter=';'):
                    ticker = _ticker_linha_mestre(row)
                    cnpj = (row.get('cnpj_fundo') or row.get('cnpj') or '').strip()
                    if ticker and cnpj:
                        mapa[ticker] = cnpj
            print(f"[cnpj] Tabela mestre carregada: {len(mapa)} tickers.")
            return mapa
        except Exception as e:
            print(f"[cnpj] Erro ao carregar tabela mestre: {e}")
    return {}


def _row_get(row, chave: str, padrao=None):
    if not row:
        return padrao
    if isinstance(row, dict):
        return row.get(chave, padrao)
    if hasattr(row, "keys") and chave in row.keys():
        return row[chave]
    return padrao


def _ticker_do_isin(isin: str) -> str | None:
    match = re.match(r'BR([A-Z0-9]{4,6})CTF', isin.upper())
    return (match.group(1) + "11") if match else None


def _carregar_cvm(ano: int) -> dict[str, str]:
    for ext in ('csv', 'zip'):
        url = f"{_BASE_CVM}/inf_mensal_fii_geral_{ano}.{ext}"
        try:
            r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            if r.status_code != 200:
                continue
            conteudo = ""
            if ext == 'zip':
                with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                    csvs = [n for n in z.namelist() if n.endswith('.csv')]
                    if not csvs:
                        continue
                    conteudo = z.open(csvs[0]).read().decode('latin-1')
            else:
                r.encoding = 'latin-1'
                conteudo = r.text
            mapa = {}
            for row in csv.DictReader(io.StringIO(conteudo), delimiter=';'):
                isin = row.get('Codigo_ISIN', '').strip()
                cnpj = row.get('CNPJ_Fundo_Classe', '').strip()
                ticker = _ticker_do_isin(isin)
                if ticker and cnpj and ticker not in mapa:
                    mapa[ticker] = cnpj
            if mapa:
                print(f"[cnpj] CVM {ano} ({ext}): {len(mapa)} tickers.")
                return mapa
        except Exception as e:
            print(f"[cnpj] Erro CVM {ano}.{ext}: {e}")
    return {}


def _carregar_cache() -> dict[str, str]:
    global _cache
    if _cache:
        return _cache
    mapa = _carregar_tabela_mestre()
    if not mapa:
        ano = date.today().year
        mapa = _carregar_cvm(ano) or _carregar_cvm(ano - 1)
    _cache = mapa
    return mapa


def obter_cnpj(ticker: str) -> str | None:
    ticker = ticker.upper().strip()

    try:
        from coleta import tabela_mestre_fiis

        item = tabela_mestre_fiis.obter_por_ticker(ticker)
        cnpj = item.get("cnpj_fundo") if item else None
        if cnpj:
            return cnpj
    except Exception:
        pass

    try:
        row = db.buscar_um("SELECT cnpj FROM fiis WHERE ticker = ?", (ticker,))
        cnpj = _row_get(row, "cnpj")
        if cnpj:
            return cnpj
    except Exception:
        pass
    cnpj = _carregar_cache().get(ticker)
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
