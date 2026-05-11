"""
coleta/relatorio_fnet.py
Coleta e extrai o último Relatório Gerencial de um FII direto da FNET (B3).

Fluxo:
  1. Busca o ID do documento mais recente via API FNET
  2. Baixa o PDF em memória
  3. Extrai texto com pdfplumber (preserva layout e tabelas)
  4. Limpa e trunca para caber no contexto do Gemini (~12.000 chars)
  5. Cacheia resultado no SQLite por 24h para não baixar o mesmo PDF toda vez

Dependências novas (adicionar ao requirements.txt):
  pdfplumber
"""

import io
import re
import time
from datetime import date, datetime, timedelta, timezone

import pdfplumber
import requests

import banco.db as db

# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

_FNET_BASE_URL = "https://fnet.bmfbovespa.com.br/fnet/publico/pesquisarGerenciadorDocumentosDados"

_FNET_DOWNLOAD = (
    "https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id={doc_id}"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://fnet.bmfbovespa.com.br/fnet/publico/pesquisarGerenciadorDocumentos",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://fnet.bmfbovespa.com.br",
    "Connection": "keep-alive",
}

_TIMEOUT        = 20
_MAX_CHARS      = 12_000
_CACHE_HORAS    = 24


# ─────────────────────────────────────────────────────────────────────────────
# Cache SQLite — tabela relatorios_cache
# ─────────────────────────────────────────────────────────────────────────────

_SQL_CREATE_CACHE = """
CREATE TABLE IF NOT EXISTS relatorios_cache (
    ticker      TEXT PRIMARY KEY,
    doc_id      TEXT,
    data_doc    TEXT,
    texto       TEXT,
    coletado_em TEXT
);
"""

def _garantir_tabela():
    db.executar(_SQL_CREATE_CACHE)


def _ler_cache(ticker: str) -> str | None:
    """Retorna texto do cache se ainda válido (< 24h). Caso contrário None."""
    _garantir_tabela()
    row = db.buscar_um(
        "SELECT texto, coletado_em FROM relatorios_cache WHERE ticker = ?",
        (ticker,)
    )
    if not row:
        return None
    from datetime import timezone, timedelta
    coletado = datetime.fromisoformat(row["coletado_em"]).replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - coletado < timedelta(hours=_CACHE_HORAS):
        return row["texto"]
    return None


def _salvar_cache(ticker: str, doc_id: str, data_doc: str, texto: str):
    _garantir_tabela()
    from datetime import timezone
    db.executar(
        """
        INSERT OR REPLACE INTO relatorios_cache (ticker, doc_id, data_doc, texto, coletado_em)
        VALUES (?, ?, ?, ?, ?)
        """,
        (ticker, doc_id, data_doc, texto, datetime.now(timezone.utc).isoformat())
    )


# ─────────────────────────────────────────────────────────────────────────────
# Busca do documento mais recente na FNET
# ─────────────────────────────────────────────────────────────────────────────

def _buscar_doc_id(ticker: str) -> tuple[str, str] | tuple[None, None]:
    """
    Retorna (doc_id, data_referencia) do relatório gerencial mais recente.

    Estratégia:
      1. Tenta buscar por CNPJ (mais preciso, evita bloqueio por texto)
      2. Fallback: busca por palavrasChave (ticker como texto)
    """
    from coleta.cnpj_fundo import obter_cnpj

    cnpj = obter_cnpj(ticker)

    # Monta params — CNPJ tem prioridade sobre palavrasChave
    if cnpj:
        cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
        params = {
            "d": "0", "o": "1", "f": "1", "l": "5", "c": "4",
            "tipoFundo": "FII",
            "idTipoDocumento": "41",
            "idEspecieDocumento": "0",
            "cnpjFundo": cnpj_limpo,
            "search[value]": "",
            "search[regex]": "false",
            "ativo": "true",
        }
    else:
        params = {
            "d": "0", "o": "1", "f": "1", "l": "5", "c": "4",
            "tipoFundo": "FII",
            "idTipoDocumento": "41",
            "idEspecieDocumento": "0",
            "palavrasChave": ticker,
            "search[value]": "",
            "search[regex]": "false",
            "ativo": "true",
        }

    try:
        resp = requests.get(_FNET_BASE_URL, params=params, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        dados = resp.json()
    except Exception as e:
        print(f"[fnet] Erro ao buscar documentos de {ticker}: {e}")
        return None, None

    documentos = dados.get("data", [])
    if not documentos:
        print(f"[fnet] Nenhum relatório gerencial encontrado para {ticker}.")
        return None, None

    doc = documentos[0]
    doc_id   = str(doc.get("id", ""))
    data_ref = doc.get("dataReferencia") or doc.get("dataEntrega") or ""

    if not doc_id:
        return None, None

    return doc_id, data_ref


# ─────────────────────────────────────────────────────────────────────────────
# Download e extração do PDF
# ─────────────────────────────────────────────────────────────────────────────

def _baixar_e_extrair(doc_id: str) -> str | None:
    """Baixa o PDF em memória e extrai o texto com pdfplumber."""
    url = _FNET_DOWNLOAD.format(doc_id=doc_id)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, stream=True)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type.lower() and "octet-stream" not in content_type.lower():
            print(f"[fnet] Resposta inesperada (não é PDF): {content_type}")
            return None

        pdf_bytes = resp.content

    except Exception as e:
        print(f"[fnet] Erro ao baixar PDF (doc_id={doc_id}): {e}")
        return None

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            paginas = []
            for i, pagina in enumerate(pdf.pages):
                texto_pag = pagina.extract_text(x_tolerance=2, y_tolerance=3) or ""

                # Tabelas inline (vacância, carteira de imóveis, etc.)
                tabelas = pagina.extract_tables()
                for tabela in tabelas:
                    for linha in tabela:
                        linha_limpa = " | ".join(
                            (c or "").strip() for c in linha if c
                        )
                        if linha_limpa.strip():
                            texto_pag += "\n" + linha_limpa

                paginas.append(texto_pag)

                # Para PDFs grandes, limita a 20 páginas para não estourar o contexto
                if i >= 19:
                    paginas.append("[... relatório truncado após 20 páginas ...]")
                    break

        texto_bruto = "\n\n".join(paginas)
        return texto_bruto

    except Exception as e:
        print(f"[fnet] Erro ao extrair PDF (doc_id={doc_id}): {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Limpeza e truncamento do texto
# ─────────────────────────────────────────────────────────────────────────────

def _limpar_texto(texto: str) -> str:
    """Remove lixo típico de PDF (cabeçalhos repetidos, rodapés, espaços duplos)."""
    # Remove linhas que são só números (rodapé de página)
    linhas = texto.splitlines()
    linhas = [l for l in linhas if not re.fullmatch(r'\s*\d{1,3}\s*', l)]

    # Remove espaços excessivos
    texto = "\n".join(linhas)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    texto = re.sub(r'[ \t]{2,}', ' ', texto)

    return texto.strip()


def _truncar(texto: str, max_chars: int = _MAX_CHARS) -> str:
    """Mantém o início do relatório (onde ficam os destaques do gestor)."""
    if len(texto) <= max_chars:
        return texto
    return texto[:max_chars] + f"\n\n[... texto truncado - {len(texto)} chars totais ...]"


# ─────────────────────────────────────────────────────────────────────────────
# Interface pública
# ─────────────────────────────────────────────────────────────────────────────

def obter_relatorio(ticker: str) -> str:
    """
    Retorna o texto do último Relatório Gerencial do ticker.

    Ordem de prioridade:
      1. Cache SQLite válido (< 24h)
      2. Download novo da FNET

    Retorna string vazia se não conseguir obter o relatório.
    """
    ticker = ticker.upper().strip()

    # 1. Cache
    texto_cache = _ler_cache(ticker)
    if texto_cache:
        print(f"[fnet] {ticker} - relatório gerencial carregado do cache.")
        return texto_cache

    # 2. Busca doc_id
    print(f"[fnet] {ticker} - buscando último relatório gerencial na FNET...")
    doc_id, data_ref = _buscar_doc_id(ticker)
    if not doc_id:
        return ""

    print(f"[fnet] {ticker} - baixando PDF (doc_id={doc_id}, ref={data_ref})...")
    time.sleep(0.5)   # pausa gentil para não sobrecarregar a FNET

    texto_bruto = _baixar_e_extrair(doc_id)
    if not texto_bruto:
        return ""

    texto_final = _truncar(_limpar_texto(texto_bruto))

    _salvar_cache(ticker, doc_id, data_ref, texto_final)

    print(f"[fnet] {ticker} - relatório extraído: {len(texto_final)} chars.")
    return texto_final
