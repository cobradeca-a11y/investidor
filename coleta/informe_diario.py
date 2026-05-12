"""
coleta/informe_diario.py
Coleta o Informe Diario de Fundos da CVM.

Fonte: dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{AAAAMM}.zip
Dados: VL_QUOTA, VL_PATRIM_LIQ, NR_COTST por CNPJ/dia
Uso:  monitoramento diario de patrimonio e cotas — base para alertas
"""

import io
import csv
import zipfile
import requests
from datetime import date, timedelta
import banco.db as db
from coleta.cnpj_fundo import _carregar_cache as carregar_mapa_cnpj

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_TIMEOUT  = 45
_BASE_URL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS"

_SQL_CREATE = """
CREATE TABLE IF NOT EXISTS informe_diario (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker        TEXT NOT NULL,
    cnpj          TEXT NOT NULL,
    data          TEXT NOT NULL,
    vl_quota      REAL,
    vl_patrim_liq REAL,
    nr_cotistas   INTEGER,
    captacao      REAL,
    resgate       REAL,
    UNIQUE(ticker, data)
);
"""


def _garantir_tabela():
    db.executar(_SQL_CREATE)


def _url_zip(ano: int, mes: int) -> str:
    return f"{_BASE_URL}/inf_diario_fi_{ano}{mes:02d}.zip"


def _cnpj_para_ticker() -> dict[str, str]:
    """Inverte o mapa ticker→cnpj para cnpj→ticker."""
    mapa = carregar_mapa_cnpj()
    return {v: k for k, v in mapa.items()}


def coletar_mes(ano: int, mes: int) -> int:
    """
    Baixa o ZIP do informe diario do mes/ano e grava no banco.
    Retorna quantidade de registros inseridos.
    """
    _garantir_tabela()
    cnpj_to_ticker = _cnpj_para_ticker()

    if not cnpj_to_ticker:
        print("[diario] Mapa CNPJ vazio — rode popular_cnpjs_banco() primeiro.")
        return 0

    url = _url_zip(ano, mes)
    try:
        print(f"[diario] Baixando {url}...")
        r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        print(f"[diario] Erro ao baixar {ano}/{mes:02d}: {e}")
        return 0

    try:
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            csvs = [n for n in z.namelist() if n.endswith('.csv')]
            if not csvs:
                print(f"[diario] ZIP vazio para {ano}/{mes:02d}")
                return 0
            with z.open(csvs[0]) as f:
                conteudo = f.read().decode('latin-1')
    except Exception as e:
        print(f"[diario] Erro ao extrair ZIP: {e}")
        return 0

    inseridos = 0
    for row in csv.DictReader(io.StringIO(conteudo), delimiter=';'):
        cnpj = row.get('CNPJ_FUNDO', '').strip()
        ticker = cnpj_to_ticker.get(cnpj)
        if not ticker:
            continue

        try:
            db.executar(
                """
                INSERT OR IGNORE INTO informe_diario
                    (ticker, cnpj, data, vl_quota, vl_patrim_liq, nr_cotistas, captacao, resgate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker,
                    cnpj,
                    row.get('DT_COMPTC', '').strip(),
                    _float(row.get('VL_QUOTA')),
                    _float(row.get('VL_PATRIM_LIQ')),
                    _int(row.get('NR_COTST')),
                    _float(row.get('CAPTC_DIA')),
                    _float(row.get('RESG_DIA')),
                )
            )
            inseridos += 1
        except Exception:
            pass

    print(f"[diario] {ano}/{mes:02d}: {inseridos} registros gravados.")
    return inseridos


def coletar_mes_atual() -> int:
    hoje = date.today()
    return coletar_mes(hoje.year, hoje.month)


def coletar_mes_anterior() -> int:
    primeiro = date.today().replace(day=1)
    ultimo_mes = primeiro - timedelta(days=1)
    return coletar_mes(ultimo_mes.year, ultimo_mes.month)


def _float(v) -> float | None:
    try:
        return float(str(v).replace(',', '.').strip())
    except Exception:
        return None


def _int(v) -> int | None:
    try:
        return int(str(v).strip())
    except Exception:
        return None


def ultimo_patrimonio(ticker: str) -> dict | None:
    """Retorna o ultimo registro diario disponivel para o ticker."""
    row = db.buscar_um(
        """
        SELECT * FROM informe_diario
        WHERE ticker = ?
        ORDER BY data DESC LIMIT 1
        """,
        (ticker,)
    )
    return dict(row) if row else None


def variacao_patrimonio(ticker: str, dias: int = 30) -> float | None:
    """Retorna variacao percentual do patrimonio liquido nos ultimos N dias."""
    rows = db.buscar_todos(
        """
        SELECT vl_patrim_liq FROM informe_diario
        WHERE ticker = ? AND vl_patrim_liq IS NOT NULL
        ORDER BY data DESC LIMIT ?
        """,
        (ticker, dias)
    )
    if len(rows) < 2:
        return None
    recente = rows[0]['vl_patrim_liq']
    antigo  = rows[-1]['vl_patrim_liq']
    if not antigo:
        return None
    return round((recente / antigo - 1) * 100, 2)
