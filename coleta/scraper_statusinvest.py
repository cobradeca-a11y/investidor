"""
coleta/scraper_statusinvest.py
Coleta indicadores de FIIs no Status Invest.
Inclui cálculo de score de confiabilidade dos dados coletados.
"""
import requests
from bs4 import BeautifulSoup
from datetime import date
from typing import Optional
from config.settings import URL_STATUS_INVEST
from banco import db


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}


def _parse_numero(texto: Optional[str]) -> Optional[float]:
    """Converte texto brasileiro para float. Ex: '1.234,56' → 1234.56"""
    if not texto:
        return None
    texto = texto.strip().replace("%", "").replace("R$", "").strip()
    if texto in ("-", "N/A", ""):
        return None
    try:
        # Remove pontos de milhar, troca vírgula por ponto
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _calcular_confiabilidade(dados: dict) -> int:
    """
    Calcula score de confiabilidade de 0 a 100.
    Penaliza campos ausentes proporcionalmente ao peso de cada um.
    """
    campos_peso = {
        "preco":               20,
        "pvp":                 15,
        "dy_12m":              15,
        "liquidez_diaria":     15,
        "ultimo_dividendo":    10,
        "patrimonio_liquido":  10,
        "vpa":                  5,
        "vacancia_fisica":      5,
        "vacancia_financeira":  5,
    }
    total_peso = sum(campos_peso.values())
    pontos = 0
    for campo, peso in campos_peso.items():
        if dados.get(campo) is not None:
            pontos += peso

    return int((pontos / total_peso) * 100)


def coletar_fii(ticker: str) -> Optional[dict]:
    """
    Coleta indicadores de um FII no Status Invest.
    Retorna dict com os dados ou None em caso de falha.
    """
    ticker = ticker.upper().strip()
    hoje = date.today().isoformat()

    # Verifica se já coletou hoje
    existente = db.buscar_um(
        "SELECT * FROM indicadores WHERE ticker = ? AND data = ?",
        (ticker, hoje)
    )
    if existente:
        print(f"[statusinvest] {ticker} já coletado para {hoje}")
        return dict(existente)

    url = URL_STATUS_INVEST.format(ticker=ticker.lower())

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[statusinvest] Erro ao acessar {ticker}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    def _valor_por_titulo(titulo: str) -> Optional[float]:
        """Busca valor no padrão de card do Status Invest."""
        for tag in soup.find_all(["span", "strong", "div"]):
            if titulo.lower() in tag.get_text(strip=True).lower():
                # Tenta pegar o próximo valor numérico após o label
                pai = tag.parent
                if pai:
                    textos = [
                        t.get_text(strip=True)
                        for t in pai.find_all(["strong", "b", "span"])
                        if t != tag
                    ]
                    for t in textos:
                        v = _parse_numero(t)
                        if v is not None:
                            return v
        return None

    # Extração por seletores CSS conhecidos do Status Invest
    def _css(seletor: str) -> Optional[float]:
        el = soup.select_one(seletor)
        if el:
            return _parse_numero(el.get_text(strip=True))
        return None

    dados: dict = {
        "ticker":               ticker,
        "data":                 hoje,
        "preco":                _css('[title="Valor atual"] strong') or _valor_por_titulo("Valor atual"),
        "pvp":                  _css('[title="P/VP"] strong') or _valor_por_titulo("P/VP"),
        "liquidez_diaria":      _css('[title="Liquidez"] strong') or _valor_por_titulo("Liquidez"),
        "ultimo_dividendo":     _css('[title="Último rendimento"] strong') or _valor_por_titulo("Último rendimento"),
        "dy_3m":                _valor_por_titulo("DY (3M)"),
        "dy_6m":                _valor_por_titulo("DY (6M)"),
        "dy_12m":               _css('[title="DY"] strong') or _valor_por_titulo("Dividend yield"),
        "dy_patrimonial":       _valor_por_titulo("DY patrimonial"),
        "vacancia_fisica":      _valor_por_titulo("Vacância física"),
        "vacancia_financeira":  _valor_por_titulo("Vacância financeira"),
        "patrimonio_liquido":   _valor_por_titulo("Patrimônio"),
        "vpa":                  _css('[title="VPA"] strong') or _valor_por_titulo("VPA"),
        "qtd_ativos":           None,
        "fonte":                "statusinvest",
    }

    # Converte DY de percentual para decimal se necessário
    for campo in ["dy_3m", "dy_6m", "dy_12m", "dy_patrimonial",
                  "vacancia_fisica", "vacancia_financeira"]:
        v = dados.get(campo)
        if v is not None and v > 1:   # está em %, converte para decimal
            dados[campo] = v / 100

    dados["confiabilidade"] = _calcular_confiabilidade(dados)

    # Garante que o FII existe na tabela fiis
    db.inserir("fiis", {"ticker": ticker, "nome": ticker, "tipo": "INDEFINIDO", "segmento": "INDEFINIDO"})

    # Salva no banco
    db.upsert("indicadores", dados)

    print(
        f"[statusinvest] {ticker} coletado → "
        f"Preço: R${dados.get('preco')} | "
        f"P/VP: {dados.get('pvp')} | "
        f"DY12M: {dados.get('dy_12m')} | "
        f"Confiabilidade: {dados['confiabilidade']}%"
    )
    return dados
