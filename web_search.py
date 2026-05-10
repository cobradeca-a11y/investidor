"""
coleta/web_search.py
Busca notícias de FIIs para análise qualitativa da IA.

Estratégia:
  1. Google News RSS  (primário  — gratuito, sem autenticação)
  2. DuckDuckGo DDGS  (fallback  — pode falhar por rate limit / bloqueio)
  3. Texto vazio      (saída segura — IA continua sem notícias)
"""

import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

_GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search"
    "?q={query}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}
_TIMEOUT = 10       # segundos por requisição
_MAX_NOTICIAS = 8   # total de notícias a retornar


# ─────────────────────────────────────────────────────────────────────────────
# Fonte primária: Google News RSS
# ─────────────────────────────────────────────────────────────────────────────

def _buscar_google_news(ticker: str) -> list[dict]:
    """Retorna lista de dicts {titulo, data, resumo} via Google News RSS."""
    query = urllib.parse.quote(f"{ticker} FII notícias")
    url = _GOOGLE_NEWS_RSS.format(query=query)

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[web_search] Google News falhou: {exc}")
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as exc:
        print(f"[web_search] Erro ao parsear RSS: {exc}")
        return []

    noticias = []
    for item in root.findall(".//item"):
        titulo  = item.findtext("title", "").strip()
        pub_raw = item.findtext("pubDate", "").strip()
        resumo  = item.findtext("description", "").strip()

        # Limpa tags HTML simples que aparecem no <description>
        resumo = resumo.replace("<![CDATA[", "").replace("]]>", "")

        # Formata data legível
        try:
            dt = datetime.strptime(pub_raw, "%a, %d %b %Y %H:%M:%S %Z")
            data = dt.strftime("%d/%m/%Y")
        except ValueError:
            data = pub_raw[:10] if pub_raw else "data desconhecida"

        if titulo:
            noticias.append({"titulo": titulo, "data": data, "resumo": resumo})

        if len(noticias) >= _MAX_NOTICIAS:
            break

    return noticias


# ─────────────────────────────────────────────────────────────────────────────
# Fallback: DuckDuckGo
# ─────────────────────────────────────────────────────────────────────────────

def _buscar_duckduckgo(ticker: str) -> list[dict]:
    """Fallback via DDGS. Silencia erros para não travar o radar."""
    try:
        from duckduckgo_search import DDGS  # importação lazy
        resultados = DDGS().news(f"{ticker} noticias", max_results=_MAX_NOTICIAS)
        return [
            {
                "titulo": r.get("title", ""),
                "data":   r.get("date", "")[:10],
                "resumo": r.get("body", ""),
            }
            for r in resultados
            if r.get("title")
        ]
    except Exception as exc:
        print(f"[web_search] DuckDuckGo falhou: {exc}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Interface pública
# ─────────────────────────────────────────────────────────────────────────────

def buscar_noticias(ticker: str) -> str:
    """
    Retorna texto consolidado de notícias para o ticker informado.
    Tenta Google News RSS primeiro; cai no DuckDuckGo se necessário.
    Retorna string vazia se ambas as fontes falharem.
    """
    ticker = ticker.upper().strip()

    noticias = _buscar_google_news(ticker)

    if not noticias:
        print(f"[web_search] Tentando DuckDuckGo como fallback para {ticker}...")
        time.sleep(1)   # pequena pausa antes do fallback
        noticias = _buscar_duckduckgo(ticker)

    if not noticias:
        print(f"[web_search] Nenhuma notícia encontrada para {ticker}.")
        return ""

    linhas = [f"Notícias recentes sobre {ticker}:\n"]
    for i, n in enumerate(noticias, 1):
        linhas.append(f"{i}. [{n['data']}] {n['titulo']}")
        if n["resumo"]:
            linhas.append(f"   {n['resumo'][:300]}")
        linhas.append("")

    return "\n".join(linhas)
