"""
coleta/informe_trimestral.py
Coleta o Informe Trimestral de FIIs da CVM.

Fonte: dados.cvm.gov.br/dados/FII/DOC/INF_TRIMESTRAL/DADOS/inf_trimestral_fii_{ANO}.zip
Dados extraidos:
  - Vacancia real por imovel (inf_trimestral_fii_imovel)
  - Vencimento de contratos por faixa (inf_trimestral_fii_complemento)
  - Aquisicoes e alienacoes de imoveis
  - Resultado contabil/financeiro

Uso no FIIA:
  - Preenche vacancia_fisica quando o Fundamentus nao retorna
  - Alimenta contexto qualitativo da IA com dados oficiais
  - Detecta vencimentos proximos de contratos (risco de vacancia futura)
"""

import io, csv, zipfile, requests
from datetime import date
import banco.db as db
from coleta.cnpj_fundo import obter_cnpj

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_TIMEOUT  = 45
_BASE_URL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_TRIMESTRAL/DADOS"

_SQL_IMOVEIS = """
CREATE TABLE IF NOT EXISTS inf_trimestral_imoveis (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT NOT NULL,
    cnpj             TEXT NOT NULL,
    data_referencia  TEXT NOT NULL,
    nome_imovel      TEXT,
    classe           TEXT,
    area             REAL,
    vacancia_pct     REAL,
    inadimplencia_pct REAL,
    receita_pct      REAL,
    locado_pct       REAL,
    UNIQUE(cnpj, data_referencia, nome_imovel)
);
"""

_SQL_CONTRATOS = """
CREATE TABLE IF NOT EXISTS inf_trimestral_contratos (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT NOT NULL,
    cnpj             TEXT NOT NULL,
    data_referencia  TEXT NOT NULL,
    venc_ate_3m      REAL,
    venc_3a6m        REAL,
    venc_6a12m       REAL,
    venc_acima_36m   REAL,
    indexador_igpm   REAL,
    indexador_ipca   REAL,
    UNIQUE(cnpj, data_referencia)
);
"""


def _garantir_tabelas():
    db.executar(_SQL_IMOVEIS)
    db.executar(_SQL_CONTRATOS)


def _baixar_zip(ano: int) -> bytes | None:
    url = f"{_BASE_URL}/inf_trimestral_fii_{ano}.zip"
    try:
        print(f"[trimestral] Baixando {url}...")
        r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"[trimestral] Erro ao baixar {ano}: {e}")
        return None


def _float(v) -> float | None:
    try:
        return float(str(v).replace(',', '.').strip()) if v else None
    except Exception:
        return None


def _cnpj_para_ticker(cnpj: str, mapa: dict) -> str | None:
    return mapa.get(cnpj) or mapa.get(cnpj.replace('.','').replace('/','').replace('-',''))


def coletar_ano(ano: int) -> dict:
    """
    Baixa o ZIP do informe trimestral e grava imoveis e contratos no banco.
    Retorna {'imoveis': N, 'contratos': N}
    """
    _garantir_tabelas()

    dados = _baixar_zip(ano)
    if not dados:
        return {'imoveis': 0, 'contratos': 0}

    # Mapa CNPJ → ticker (invertido da tabela mestre)
    from coleta.cnpj_fundo import _carregar_cache
    mapa_ticker_cnpj = _carregar_cache()
    mapa_cnpj_ticker = {v: k for k, v in mapa_ticker_cnpj.items()}
    # Adiciona versão sem pontuação
    for cnpj, ticker in list(mapa_cnpj_ticker.items()):
        mapa_cnpj_ticker[cnpj.replace('.','').replace('/','').replace('-','')] = ticker

    imoveis_gravados   = 0
    contratos_gravados = 0

    with zipfile.ZipFile(io.BytesIO(dados)) as z:

        # ── Imóveis ──────────────────────────────────────────────────
        fname_imovel = f"inf_trimestral_fii_imovel_{ano}.csv"
        if fname_imovel in z.namelist():
            with z.open(fname_imovel) as f:
                rows = list(csv.DictReader(io.TextIOWrapper(f, encoding='latin-1'), delimiter=';'))

            for row in rows:
                cnpj   = row.get('CNPJ_Fundo_Classe', '').strip()
                ticker = _cnpj_para_ticker(cnpj, mapa_cnpj_ticker) or cnpj
                try:
                    db.executar(
                        """INSERT OR IGNORE INTO inf_trimestral_imoveis
                           (ticker,cnpj,data_referencia,nome_imovel,classe,area,
                            vacancia_pct,inadimplencia_pct,receita_pct,locado_pct)
                           VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (
                            ticker, cnpj,
                            row.get('Data_Referencia',''),
                            row.get('Nome_Imovel',''),
                            row.get('Classe',''),
                            _float(row.get('Area')),
                            _float(row.get('Percentual_Vacancia')),
                            _float(row.get('Percentual_Inadimplencia')),
                            _float(row.get('Percentual_Receitas_FII')),
                            _float(row.get('Percentual_Locado')),
                        )
                    )
                    imoveis_gravados += 1
                except Exception:
                    pass

        # ── Complemento (vencimentos de contratos) ───────────────────
        fname_comp = f"inf_trimestral_fii_complemento_{ano}.csv"
        if fname_comp in z.namelist():
            with z.open(fname_comp) as f:
                rows = list(csv.DictReader(io.TextIOWrapper(f, encoding='latin-1'), delimiter=';'))

            for row in rows:
                cnpj   = row.get('CNPJ_Fundo_Classe', '').strip()
                ticker = _cnpj_para_ticker(cnpj, mapa_cnpj_ticker) or cnpj
                try:
                    db.executar(
                        """INSERT OR IGNORE INTO inf_trimestral_contratos
                           (ticker,cnpj,data_referencia,venc_ate_3m,venc_3a6m,
                            venc_6a12m,venc_acima_36m,indexador_igpm,indexador_ipca)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (
                            ticker, cnpj,
                            row.get('Data_Referencia',''),
                            _float(row.get('Percentual_Vencimento_Receita_FII_Faixa_Ate_3Meses')),
                            _float(row.get('Percentual_Vencimento_Receita_FII_Faixa_3a6Meses')),
                            _float(row.get('Percentual_Vencimento_Receita_FII_Faixa_6a9Meses')),
                            _float(row.get('Percentual_Vencimento_Receita_FII_Faixa_Acima_36Meses')),
                            _float(row.get('Percentual_Indexador_Receita_FII_IGPM')),
                            _float(row.get('Percentual_Indexador_Receita_FII_IPCA')),
                        )
                    )
                    contratos_gravados += 1
                except Exception:
                    pass

    print(f"[trimestral] {ano}: {imoveis_gravados} imóveis, {contratos_gravados} contratos gravados.")
    return {'imoveis': imoveis_gravados, 'contratos': contratos_gravados}


def coletar_atual() -> dict:
    ano = date.today().year
    resultado = coletar_ano(ano)
    if resultado['imoveis'] == 0:
        resultado = coletar_ano(ano - 1)
    return resultado


def vacancia_media(ticker: str) -> float | None:
    """
    Retorna a vacancia media ponderada por area do ultimo trimestre disponivel.
    """
    rows = db.buscar_todos(
        """
        SELECT vacancia_pct, area FROM inf_trimestral_imoveis
        WHERE ticker = ?
        AND data_referencia = (
            SELECT MAX(data_referencia) FROM inf_trimestral_imoveis WHERE ticker = ?
        )
        AND vacancia_pct IS NOT NULL
        """,
        (ticker, ticker)
    )
    if not rows:
        return None
    total_area = sum(r['area'] or 1 for r in rows)
    if total_area == 0:
        return None
    vac_pond = sum((r['vacancia_pct'] or 0) * (r['area'] or 1) for r in rows) / total_area
    return round(vac_pond, 2)


def risco_vencimento(ticker: str) -> dict | None:
    """
    Retorna percentual de contratos vencendo nos proximos 12 meses.
    Alto risco: > 20% da receita com vencimento em ate 12 meses.
    """
    row = db.buscar_um(
        """
        SELECT venc_ate_3m, venc_3a6m, venc_6a12m
        FROM inf_trimestral_contratos
        WHERE ticker = ?
        ORDER BY data_referencia DESC LIMIT 1
        """,
        (ticker,)
    )
    if not row:
        return None
    venc_12m = (row.get('venc_ate_3m') or 0) + (row.get('venc_3a6m') or 0) + (row.get('venc_6a12m') or 0)
    return {
        'venc_12m_pct': round(venc_12m * 100, 1),
        'risco': 'ALTO' if venc_12m > 0.20 else 'MEDIO' if venc_12m > 0.10 else 'BAIXO',
    }


def contexto_trimestral(ticker: str) -> str:
    """
    Retorna texto formatado para uso no prompt do Gemini.
    """
    vac = vacancia_media(ticker)
    risco = risco_vencimento(ticker)

    imoveis = db.buscar_todos(
        """
        SELECT nome_imovel, classe, area, vacancia_pct, inadimplencia_pct
        FROM inf_trimestral_imoveis
        WHERE ticker = ?
        ORDER BY data_referencia DESC, receita_pct DESC
        LIMIT 10
        """,
        (ticker,)
    )

    if not imoveis and vac is None:
        return ""

    linhas = [f"\nDADOS TRIMESTRAIS OFICIAIS (CVM) — {ticker}",
              "─" * 50]

    if vac is not None:
        linhas.append(f"Vacância média ponderada: {vac:.1f}%")

    if risco:
        linhas.append(f"Contratos vencendo em 12 meses: {risco['venc_12m_pct']:.1f}% da receita — risco {risco['risco']}")

    if imoveis:
        linhas.append("\nPortfólio de imóveis:")
        for im in imoveis[:5]:
            vac_im = f"{float(im['vacancia_pct'])*100:.1f}%" if im.get('vacancia_pct') is not None else "N/D"
            linhas.append(f"  • {im.get('nome_imovel','?')} | Vacância: {vac_im} | Classe: {im.get('classe','?')}")

    return "\n".join(linhas)
