"""
coleta/relatorio_fnet.py
Coleta o Relatorio Gerencial de FIIs via FNET.

Correcoes aplicadas com base no teste_fnet_cnpj.py v3:
  - Parametro correto: cnpj (nao cnpjFundo)
  - tipoFundo: '1' (nao 'FII')
  - Paginacao: d/s/l (nao draw/start/length)
  - Referer: abrirGerenciadorDocumentosCVM
  - Sessao com retry robusto

Estrategia:
  1. Busca por CNPJ do fundo (tabela mestre ou CVM)
  2. Filtra pelo documento mais recente (idTipoDocumento=40 = Informe Mensal)
  3. Baixa PDF e extrai texto com pdfplumber
  4. Cacheia no SQLite por 24h
"""

import io, re, time
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

import pdfplumber
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import banco.db as db
from coleta import cvm_fnet_documentos
from coleta.cnpj_fundo import obter_cnpj

_FNET_GRID = "https://fnet.bmfbovespa.com.br/fnet/publico/pesquisarGerenciadorDocumentosDados"
_FNET_PDF  = "https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id={doc_id}"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://fnet.bmfbovespa.com.br",
    "Connection": "keep-alive",
}

_TIMEOUT      = (5, 20)
_MAX_CHARS    = 12_000
_CACHE_HORAS  = 24
_SIMILARIDADE = 0.50
_PDF_MIN_BYTES = 200


def _criar_sessao() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2, connect=2, read=2, status=2,
        backoff_factor=1.2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    return session

_session = _criar_sessao()


# ── Cache ─────────────────────────────────────────────────────────────────────

_SQL_CACHE = """CREATE TABLE IF NOT EXISTS relatorios_cache (
    ticker TEXT PRIMARY KEY, doc_id TEXT, data_doc TEXT,
    texto TEXT, coletado_em TEXT
);"""

def _garantir_tabela():
    db.executar(_SQL_CACHE)

def _ler_cache(ticker: str) -> str | None:
    _garantir_tabela()
    row = db.buscar_um("SELECT texto, coletado_em FROM relatorios_cache WHERE ticker = ?", (ticker,))
    if not row:
        return None
    coletado = datetime.fromisoformat(row["coletado_em"]).replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - coletado < timedelta(hours=_CACHE_HORAS):
        return row["texto"]
    return None

def _salvar_cache(ticker, doc_id, data_doc, texto):
    _garantir_tabela()
    db.executar(
        "INSERT OR REPLACE INTO relatorios_cache (ticker,doc_id,data_doc,texto,coletado_em) VALUES (?,?,?,?,?)",
        (ticker, doc_id, data_doc, texto, datetime.now(timezone.utc).isoformat())
    )


# ── Busca na FNET ─────────────────────────────────────────────────────────────

def _cnpj_limpo(cnpj: str) -> str:
    return re.sub(r'\D', '', cnpj)

def _similaridade(a: str, b: str) -> float:
    return SequenceMatcher(None, a.upper(), b.upper()).ratio()


def _doc_id_persistido(documento: dict | None) -> str | None:
    if not documento:
        return None
    protocolo = documento.get("protocolo")
    if protocolo:
        return str(protocolo)
    url = documento.get("url_documento") or ""
    match = re.search(r"[?&]id=(\d+)", str(url))
    return match.group(1) if match else None


def _registrar_doc_fnet(ticker: str, cnpj: str, doc: dict) -> None:
    try:
        cvm_fnet_documentos.registrar_documento(
            {
                **doc,
                "ticker": ticker,
                "cnpj_fundo": cnpj,
                "url_documento": _FNET_PDF.format(doc_id=doc.get("id")) if doc.get("id") else None,
            },
            arquivo_origem="FNET_API_RELATORIO",
        )
    except Exception:
        return

def _buscar_doc_id(ticker: str, cnpj: str, nome_fundo: str) -> tuple[str, str] | tuple[None, None]:
    """Busca por CNPJ primeiro; fallback por nome."""
    cnpj_num = _cnpj_limpo(cnpj)

    # Tentativas: com CNPJ limpo, com CNPJ formatado, sem CNPJ (filtro local por nome)
    variantes = [
        {"d":1,"s":0,"l":20,"tipoFundo":"1","cnpj":cnpj_num,
         "idCategoriaDocumento":"6","idTipoDocumento":"40","idEspecieDocumento":"0","paginaCertificados":"false"},
        {"d":1,"s":0,"l":20,"tipoFundo":"1","cnpj":cnpj,
         "idCategoriaDocumento":"6","idTipoDocumento":"40","idEspecieDocumento":"0","paginaCertificados":"false"},
    ]

    for params in variantes:
        try:
            r = _session.get(_FNET_GRID, params=params, headers=_HEADERS, timeout=_TIMEOUT)
            if r.status_code != 200:
                continue
            data = r.json()
            docs = data.get("data", [])
            total = data.get("recordsTotal", 0)
            if docs and total > 0:
                # Filtra pelo mais recente com nome similar
                for doc in docs:
                    desc = doc.get("descricaoFundo", "") or ""
                    if _similaridade(nome_fundo, desc) >= _SIMILARIDADE or cnpj_num in desc.replace('.','').replace('/','').replace('-',''):
                        doc_id   = str(doc.get("id", ""))
                        data_ref = doc.get("dataReferencia", "")
                        _registrar_doc_fnet(ticker, cnpj, doc)
                        print(f"[fnet] {ticker} — doc_id={doc_id} | '{desc[:50]}'")
                        return doc_id, data_ref
                # Sem match de nome — usa o primeiro mesmo assim
                doc = docs[0]
                _registrar_doc_fnet(ticker, cnpj, doc)
                return str(doc.get("id", "")), doc.get("dataReferencia", "")
        except Exception as e:
            print(f"[fnet] Erro na busca ({params.get('cnpj','')}): {e}")
        time.sleep(0.5)

    # Fallback: sem CNPJ, busca geral + filtro local por nome
    try:
        params = {"d":1,"s":0,"l":100,"tipoFundo":"1","idCategoriaDocumento":"6",
                  "idTipoDocumento":"40","idEspecieDocumento":"0","paginaCertificados":"false"}
        r = _session.get(_FNET_GRID, params=params, headers=_HEADERS, timeout=_TIMEOUT)
        if r.status_code == 200:
            docs = r.json().get("data", [])
            for doc in docs:
                desc = doc.get("descricaoFundo", "") or ""
                if _similaridade(nome_fundo, desc) >= _SIMILARIDADE:
                    doc_id = str(doc.get("id", ""))
                    _registrar_doc_fnet(ticker, cnpj, doc)
                    print(f"[fnet] {ticker} — fallback nome | doc_id={doc_id}")
                    return doc_id, doc.get("dataReferencia", "")
    except Exception as e:
        print(f"[fnet] Erro no fallback: {e}")

    return None, None


# ── PDF ───────────────────────────────────────────────────────────────────────

def _extrair_pdf(doc_id: str) -> str | None:
    url = _FNET_PDF.format(doc_id=doc_id)
    try:
        r = _session.get(url, headers=_HEADERS, timeout=(5, 30), stream=True)
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:
        print(f"[fnet] Erro ao baixar PDF id={doc_id}: {e}")
        return None

    content_type = (r.headers.get("Content-Type") or "").lower()
    if not _parece_pdf(pdf_bytes, content_type):
        motivo = _motivo_resposta_nao_pdf(pdf_bytes, content_type)
        print(f"[fnet] Documento id={doc_id} ignorado: {motivo}.")
        return None

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            paginas = []
            for i, pag in enumerate(pdf.pages):
                texto = pag.extract_text(x_tolerance=2, y_tolerance=3) or ""
                for tab in pag.extract_tables():
                    for linha in tab:
                        linha_str = " | ".join((c or "").strip() for c in linha if c)
                        if linha_str.strip():
                            texto += "\n" + linha_str
                paginas.append(texto)
                if i >= 19:
                    paginas.append("[... truncado ...]")
                    break
        texto_final = "\n\n".join(paginas)
        texto_final = re.sub(r'\n{3,}', '\n\n', re.sub(r'[ \t]{2,}', ' ', texto_final)).strip()
        if len(texto_final) > _MAX_CHARS:
            texto_final = texto_final[:_MAX_CHARS] + "\n\n[... truncado ...]"
        return texto_final
    except Exception as e:
        print(f"[fnet] Erro ao extrair PDF: {e}")
        return None


def _parece_pdf(conteudo: bytes, content_type: str = "") -> bool:
    if not conteudo or len(conteudo) < _PDF_MIN_BYTES:
        return False
    inicio = conteudo[:1024].lstrip()
    return inicio.startswith(b"%PDF")


def _motivo_resposta_nao_pdf(conteudo: bytes, content_type: str = "") -> str:
    if not conteudo:
        return "resposta vazia"
    if len(conteudo) < _PDF_MIN_BYTES:
        return f"resposta curta ({len(conteudo)} bytes)"
    inicio = conteudo[:80].lstrip().lower()
    if inicio.startswith(b"<!doctype") or inicio.startswith(b"<html"):
        return f"html recebido ({content_type or 'sem content-type'})"
    if inicio.startswith(b"{") or inicio.startswith(b"["):
        return f"json recebido ({content_type or 'sem content-type'})"
    return f"conteudo nao PDF ({content_type or 'sem content-type'})"


# ── Interface pública ─────────────────────────────────────────────────────────

def _valor_row(row, chave: str, padrao=None):
    if not row:
        return padrao
    if isinstance(row, dict):
        return row.get(chave, padrao)
    if hasattr(row, "keys") and chave in row.keys():
        return row[chave]
    return padrao


def obter_relatorio(ticker: str) -> str:
    ticker = ticker.upper().strip()

    cached = _ler_cache(ticker)
    if cached:
        print(f"[fnet] {ticker} — do cache.")
        return cached

    cnpj = obter_cnpj(ticker)
    if not cnpj:
        print(f"[fnet] {ticker} — CNPJ nao encontrado.")
        return ""

    # Nome do fundo para filtro de similaridade
    row = db.buscar_um("SELECT nome FROM fiis WHERE ticker = ?", (ticker,))
    nome = (_valor_row(row, "nome", "") or ticker) if row else ticker
    if nome == ticker:
        # Tenta pegar da tabela mestre via razao_social
        from coleta.cnpj_fundo import _carregar_cache as _mapa
        pass  # nome do Fundamentus ja deve estar no banco

    print(f"[fnet] {ticker} — buscando relatorio (CNPJ={cnpj})...")
    doc_local = cvm_fnet_documentos.ultimo_documento_por_cnpj(cnpj)
    doc_id = _doc_id_persistido(doc_local)
    data_ref = doc_local.get("data_referencia") if doc_local else None
    if doc_id:
        print(f"[fnet] {ticker} — usando documento FNET local id={doc_id}.")
    else:
        doc_id, data_ref = _buscar_doc_id(ticker, cnpj, nome.upper())
    if not doc_id:
        print(f"[fnet] {ticker} — nenhum documento encontrado.")
        return ""

    texto = _extrair_pdf(doc_id)
    if not texto:
        return ""

    _salvar_cache(ticker, doc_id, data_ref, texto)
    print(f"[fnet] {ticker} — {len(texto)} chars extraidos.")
    return texto
