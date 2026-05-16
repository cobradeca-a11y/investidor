"""
coleta/api_fundamentus.py
Scraper do Fundamentus para dados fundamentalistas de FIIs.

Uso operacional:
  - Fundamentus é fallback auxiliar, não fonte institucional primária.
  - Este módulo possui monitor de integridade para detectar quebra provável do HTML.
"""
from datetime import date
from typing import Optional, List

import requests
from bs4 import BeautifulSoup

from banco import db
from sistema import observabilidade

CAMPOS_CRITICOS_DETALHE = ["preco", "pvp", "dy_12m", "liquidez_diaria", "patrimonio_liquido", "vpa"]
CAMPOS_CRITICOS_MERCADO = ["preco", "dy_12m", "pvp", "liquidez"]
LIMIAR_ALERTA_NONE_DETALHE = 0.50
LIMIAR_ALERTA_NONE_MERCADO = 0.35
LIMIAR_MINIMO_ITENS_MERCADO = 20


def _limpar_valor(texto: str) -> Optional[float]:
    if not texto or texto == '-':
        return None
    t = texto.replace('.', '').replace(',', '.').replace('%', '').strip()
    try:
        return float(t)
    except ValueError:
        return None


def _taxa_none(dados: dict, campos: list[str]) -> float:
    if not campos:
        return 0.0
    ausentes = sum(1 for campo in campos if dados.get(campo) is None)
    return ausentes / len(campos)


def _registrar_integridade_detalhe(ticker: str, dados: dict) -> None:
    taxa = _taxa_none(dados, CAMPOS_CRITICOS_DETALHE)
    contexto = {
        "ticker": ticker,
        "taxa_campos_none": round(taxa, 4),
        "campos_criticos": CAMPOS_CRITICOS_DETALHE,
        "campos_ausentes": [campo for campo in CAMPOS_CRITICOS_DETALHE if dados.get(campo) is None],
    }

    if taxa >= LIMIAR_ALERTA_NONE_DETALHE:
        observabilidade.registrar_evento(
            "WARNING",
            "coleta.api_fundamentus.integridade",
            "Possível quebra no scraper de detalhe do Fundamentus: muitos campos críticos ausentes.",
            ticker=ticker,
            fonte="fundamentus",
            contexto=contexto,
        )
    else:
        observabilidade.registrar_evento(
            "INFO",
            "coleta.api_fundamentus.integridade",
            "Integridade do detalhe Fundamentus dentro do limite.",
            ticker=ticker,
            fonte="fundamentus",
            contexto=contexto,
        )


def _registrar_integridade_mercado(resultados: list[dict]) -> None:
    total = len(resultados)
    if total == 0:
        observabilidade.registrar_evento(
            "ERROR",
            "coleta.api_fundamentus.integridade",
            "Fundamentus mercado retornou zero ativos. Possível quebra de scraping ou indisponibilidade.",
            fonte="fundamentus",
            contexto={"total_ativos": 0},
        )
        return

    taxas = [_taxa_none(item, CAMPOS_CRITICOS_MERCADO) for item in resultados]
    media_none = sum(taxas) / total
    itens_ruins = sum(1 for taxa in taxas if taxa >= LIMIAR_ALERTA_NONE_MERCADO)
    pct_itens_ruins = itens_ruins / total

    contexto = {
        "total_ativos": total,
        "media_campos_none": round(media_none, 4),
        "ativos_com_muitos_none": itens_ruins,
        "pct_ativos_com_muitos_none": round(pct_itens_ruins, 4),
        "campos_criticos": CAMPOS_CRITICOS_MERCADO,
        "limiar_none": LIMIAR_ALERTA_NONE_MERCADO,
    }

    if total < LIMIAR_MINIMO_ITENS_MERCADO or pct_itens_ruins >= 0.30 or media_none >= LIMIAR_ALERTA_NONE_MERCADO:
        observabilidade.registrar_evento(
            "WARNING",
            "coleta.api_fundamentus.integridade",
            "Possível quebra no scraper de mercado do Fundamentus.",
            fonte="fundamentus",
            contexto=contexto,
        )
    else:
        observabilidade.registrar_evento(
            "INFO",
            "coleta.api_fundamentus.integridade",
            "Integridade do mercado Fundamentus dentro do limite.",
            fonte="fundamentus",
            contexto=contexto,
        )


def coletar_fii(ticker: str) -> Optional[dict]:
    """
    Coleta indicadores do FII fazendo parser direto no fundamentus.com.br.
    Retorna o dict com os dados padronizados.
    """
    ticker = ticker.upper().strip()
    hoje = date.today().isoformat()

    existente = db.buscar_um(
        "SELECT * FROM indicadores WHERE ticker = ? AND data = ?",
        (ticker, hoje),
    )
    if existente:
        print(f"[fundamentus] {ticker} já coletado para {hoje}")
        return dict(existente)

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        url = f"https://www.fundamentus.com.br/detalhes.php?papel={ticker}"
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        res.encoding = 'latin-1'

        soup = BeautifulSoup(res.text, 'html.parser')
        tabelas = soup.find_all('table')
        if len(tabelas) < 3:
            observabilidade.registrar_evento(
                "WARNING",
                "coleta.api_fundamentus",
                "Nenhuma tabela suficiente encontrada no detalhe Fundamentus.",
                ticker=ticker,
                fonte="fundamentus",
                contexto={"quantidade_tabelas": len(tabelas)},
            )
            print(f"[fundamentus] Nenhum dado encontrado para {ticker}.")
            return None

        dados_brutos = {}
        for tabela in tabelas:
            for row in tabela.find_all('tr'):
                cells = [c.text.strip().replace('?', '') for c in row.find_all(['th', 'td'])]
                for i in range(0, len(cells) - 1, 2):
                    if cells[i]:
                        dados_brutos[cells[i]] = cells[i + 1]

    except Exception as e:
        observabilidade.registrar_erro(
            "coleta.api_fundamentus",
            e,
            ticker=ticker,
            fonte="fundamentus",
            contexto={"funcao": "coletar_fii"},
        )
        print(f"[fundamentus] Erro ao buscar {ticker}: {e}")
        return None

    preco = _limpar_valor(dados_brutos.get("Cotação")) or _limpar_valor(dados_brutos.get("Cotao"))
    vpa = _limpar_valor(dados_brutos.get("VP/Cota"))
    pvp = _limpar_valor(dados_brutos.get("P/VP"))
    dy_12m = _limpar_valor(dados_brutos.get("Div. Yield"))
    if dy_12m is not None:
        dy_12m = dy_12m / 100.0

    liquidez_fii = _limpar_valor(dados_brutos.get("Vol $ méd (2m)")) or _limpar_valor(dados_brutos.get("Vol $ md (2m)"))
    patrimonio = _limpar_valor(dados_brutos.get("Patrim Líquido")) or _limpar_valor(dados_brutos.get("Patrim Lquido"))
    vacancia = _limpar_valor(dados_brutos.get("Vacância Média")) or _limpar_valor(dados_brutos.get("Vacncia Mdia"))
    qtd_ativos = _limpar_valor(dados_brutos.get("Qtd imóveis")) or _limpar_valor(dados_brutos.get("Qtd imveis"))

    dados_finais = {
        "ticker": ticker,
        "data": hoje,
        "preco": preco,
        "pvp": pvp,
        "liquidez_diaria": liquidez_fii,
        "ultimo_dividendo": None,
        "dy_3m": None,
        "dy_6m": None,
        "dy_12m": dy_12m,
        "dy_patrimonial": None,
        "vacancia_fisica": vacancia,
        "vacancia_financeira": None,
        "patrimonio_liquido": patrimonio,
        "vpa": vpa,
        "qtd_ativos": qtd_ativos,
        "fonte": "fundamentus",
    }

    _registrar_integridade_detalhe(ticker, dados_finais)

    confiabilidade = 100
    if preco is None:
        confiabilidade -= 20
    if pvp is None:
        confiabilidade -= 20
    if dy_12m is None:
        confiabilidade -= 20
    if liquidez_fii is None:
        confiabilidade -= 10
    dados_finais["confiabilidade"] = max(0, confiabilidade)

    tipo_fii = str(dados_brutos.get("Mandato", "INDEFINIDO"))
    segmento_fii = str(dados_brutos.get("Segmento", "INDEFINIDO"))
    db.inserir("fiis", {
        "ticker": ticker,
        "nome": ticker,
        "tipo": tipo_fii.upper(),
        "segmento": segmento_fii.upper(),
    })

    db.upsert("indicadores", dados_finais)

    print(
        f"[fundamentus] {ticker} coletado -> "
        f"Preço: R${preco} | P/VP: {pvp} | "
        f"DY12M: {dy_12m} | Confiabilidade: {dados_finais['confiabilidade']}%"
    )
    return dados_finais


def coletar_mercado_inteiro() -> List[dict]:
    """
    Raspa a tabela geral de FIIs do Fundamentus.
    Retorna lista de dicionários leves para pré-filtragem.
    """
    print("[radar] Varrendo o mercado inteiro no Fundamentus...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        url = "https://www.fundamentus.com.br/fii_resultado.php"
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        res.encoding = 'latin-1'

        soup = BeautifulSoup(res.text, 'html.parser')
        tabela = soup.find('table', {'id': 'tabelaResultado'})
        if not tabela:
            _registrar_integridade_mercado([])
            return []

        corpo = tabela.find('tbody')
        if not corpo:
            _registrar_integridade_mercado([])
            return []

        resultados = []
        for row in corpo.find_all('tr'):
            cols = [c.text.strip() for c in row.find_all('td')]
            if len(cols) < 13:
                continue

            dy_raw = _limpar_valor(cols[4])
            vacancia_raw = _limpar_valor(cols[12])

            resultados.append({
                "ticker": cols[0].upper(),
                "segmento": cols[1].upper(),
                "preco": _limpar_valor(cols[2]),
                "dy_12m": dy_raw / 100.0 if dy_raw is not None else None,
                "pvp": _limpar_valor(cols[5]),
                "liquidez": _limpar_valor(cols[7]) or 0.0,
                "qtd_ativos": _limpar_valor(cols[8]),
                "vacancia_media": vacancia_raw,
            })

        _registrar_integridade_mercado(resultados)
        print(f"[radar] {len(resultados)} FIIs encontrados para análise.")
        return resultados

    except Exception as e:
        observabilidade.registrar_erro(
            "coleta.api_fundamentus",
            e,
            fonte="fundamentus",
            contexto={"funcao": "coletar_mercado_inteiro"},
        )
        print(f"[radar] Erro ao varrer mercado: {e}")
        return []
