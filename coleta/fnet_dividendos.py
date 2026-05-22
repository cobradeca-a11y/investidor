"""
coleta/fnet_dividendos.py
Coletor/normalizador de rendimentos via FNET — Avisos aos Cotistas.

Objetivo:
- tornar FNET/CVM a fonte primária de dividendos quando houver metadado/documento disponível;
- manter yfinance apenas como fallback;
- persistir valor, data-base, data-com e data-pagamento com fonte rastreável.

Este módulo aceita importação de arquivo local estruturado exportado/extraído do FNET.
A extração automática de PDF fica em camada posterior de NLP/ETL documental.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from banco import db
from processamento.dividendo_recorrente import classificar_dividendos
from sistema import observabilidade

TABELA = "fnet_dividendos_fii"
_COLUNAS_TABELA = {
    "ticker",
    "cnpj_fundo",
    "data_base",
    "data_com",
    "data_pagamento",
    "valor",
    "tipo",
    "fonte",
    "protocolo",
    "url_documento",
    "assunto",
    "arquivo_origem",
    "coletado_em",
    "payload_json",
    "dedupe_key",
}
_FNET_GRID = "https://fnet.bmfbovespa.com.br/fnet/publico/pesquisarGerenciadorDocumentosDados"
_FNET_DOWNLOAD = "https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id={doc_id}"
_FNET_VISUALIZAR = "https://fnet.bmfbovespa.com.br/fnet/publico/visualizarDocumento?id={doc_id}"
_TIMEOUT = (5, 30)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://fnet.bmfbovespa.com.br",
}

_ALIASES = {
    "ticker": ["ticker", "codigo", "código", "cod_negociacao", "codigo_negociacao", "ativo"],
    "cnpj_fundo": ["cnpj_fundo", "cnpj", "CNPJ_Fundo", "CNPJ FUNDO", "cnpjEmissor"],
    "data_base": ["data_base", "dt_base", "Data Base"],
    "data_com": ["data_com", "dt_com", "Data COM"],
    "data_pagamento": ["data_pagamento", "dt_pagamento", "pagamento", "data_pgto", "Data Pagamento"],
    "valor": ["valor", "valor_por_cota", "rendimento", "rendimento_por_cota", "valor_provento", "Valor por Cota"],
    "tipo": ["tipo", "tipo_provento", "categoria", "tipo_documento"],
    "protocolo": ["protocolo", "numero_protocolo", "id", "idDocumento"],
    "url_documento": ["url_documento", "url", "link", "download", "urlDownload"],
    "assunto": ["assunto", "titulo", "descricao", "nome_documento"],
}


def _criar_sessao() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=1.2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    return session


_session = _criar_sessao()


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_get(row: Any, chave: str, padrao: Any = None) -> Any:
    try:
        return row[chave]
    except Exception:
        return padrao


def _garantir_coluna(nome_tabela: str, nome_coluna: str, definicao: str) -> None:
    colunas = db.buscar_todos(f"PRAGMA table_info({nome_tabela})")
    existentes = {_row_get(col, "name") for col in colunas}
    if nome_coluna not in existentes:
        db.executar(f"ALTER TABLE {nome_tabela} ADD COLUMN {nome_coluna} {definicao}")


def garantir_tabelas() -> None:
    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            cnpj_fundo TEXT,
            data_base TEXT,
            data_com TEXT,
            data_pagamento TEXT NOT NULL,
            valor REAL NOT NULL,
            tipo TEXT DEFAULT 'INDEFINIDO',
            fonte TEXT NOT NULL DEFAULT 'FNET_AVISO_COTISTAS',
            protocolo TEXT,
            url_documento TEXT,
            assunto TEXT,
            arquivo_origem TEXT,
            coletado_em TEXT NOT NULL,
            payload_json TEXT,
            dedupe_key TEXT
        );
        """
    )
    _garantir_coluna(TABELA, "dedupe_key", "TEXT")
    db.executar(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{TABELA}_dedupe_key ON {TABELA}(dedupe_key)")

    _garantir_coluna("dividendos", "data_base", "TEXT")
    _garantir_coluna("dividendos", "data_com", "TEXT")
    _garantir_coluna("dividendos", "protocolo", "TEXT")
    _garantir_coluna("dividendos", "url_documento", "TEXT")


def _norm_coluna(nome: str) -> str:
    return str(nome).strip().lower()


def _localizar(df: pd.DataFrame, campo: str) -> str | None:
    mapa = {_norm_coluna(c): c for c in df.columns}
    for alias in _ALIASES[campo]:
        chave = _norm_coluna(alias)
        if chave in mapa:
            return mapa[chave]
    return None


def _limpar(valor: Any) -> str | None:
    if valor is None or pd.isna(valor):
        return None
    texto = str(valor).strip()
    return texto if texto else None


def _limpar_ticker(valor: Any) -> str | None:
    texto = _limpar(valor)
    return texto.upper().replace(".SA", "") if texto else None


def _normalizar_data(valor: Any) -> str | None:
    texto = _limpar(valor)
    if not texto:
        return None
    try:
        dayfirst = not bool(re.match(r"^\d{4}-\d{2}-\d{2}", texto))
        data = pd.to_datetime(texto, dayfirst=dayfirst, errors="coerce")
        if pd.isna(data):
            return None
        return data.strftime("%Y-%m-%d")
    except Exception:
        return None


def _normalizar_float(valor: Any) -> float | None:
    texto = _limpar(valor)
    if not texto:
        return None
    texto = re.sub(r"[^0-9,.-]", "", texto)
    if texto.count(",") == 1 and texto.rfind(",") > texto.rfind("."):
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except Exception:
        return None


def _texto_xml(elemento: ET.Element | None, caminho: str) -> str | None:
    if elemento is None:
        return None
    alvo = elemento.find(caminho)
    if alvo is None or alvo.text is None:
        return None
    texto = alvo.text.strip()
    return texto or None


def _normalizar_tipo_evento(valor: str | None) -> str:
    texto = (valor or "").strip().upper()
    if "AMORT" in texto:
        return "AMORTIZACAO"
    if "RESTIT" in texto:
        return "RESTITUICAO"
    if "SUBSCR" in texto:
        return "SUBSCRICAO"
    if "REND" in texto:
        return "RENDIMENTO"
    return texto or "INDEFINIDO"


def _decodificar_resposta_fnet(conteudo: bytes) -> bytes:
    bruto = conteudo.strip().strip(b'"')
    if bruto.startswith(b"<?xml") or bruto.startswith(b"<"):
        return bruto
    try:
        decodificado = base64.b64decode(bruto, validate=True)
    except Exception:
        return bruto
    return decodificado.strip()


def extrair_eventos_xml(conteudo_xml: bytes | str) -> list[dict[str, Any]]:
    """Extrai eventos estruturados de proventos do XML oficial do FNET."""
    if isinstance(conteudo_xml, str):
        conteudo_xml = conteudo_xml.encode("utf-8")

    root = ET.fromstring(conteudo_xml)
    dados_gerais = root.find(".//DadosGerais")
    cnpj_fundo = _texto_xml(dados_gerais, "CNPJFundo")
    data_informacao = _normalizar_data(_texto_xml(dados_gerais, "DataInformacao"))
    eventos: list[dict[str, Any]] = []

    for provento in root.findall(".//Provento"):
        ticker = _limpar_ticker(_texto_xml(provento, "CodNegociacao"))
        cod_isin = _limpar(_texto_xml(provento, "CodISIN"))
        for bloco in list(provento):
            if bloco.tag in {"CodISIN", "CodNegociacao"}:
                continue
            data_base = _normalizar_data(
                _texto_xml(bloco, "DataBase")
                or _texto_xml(bloco, "DataCom")
                or _texto_xml(bloco, "DataIdentificacaoDireito")
            )
            data_pagamento = _normalizar_data(
                _texto_xml(bloco, "DataPagamento")
                or _texto_xml(bloco, "DataPgto")
                or _texto_xml(bloco, "DataPrevisaoPagamento")
            )
            valor = _normalizar_float(
                _texto_xml(bloco, "ValorProvento")
                or _texto_xml(bloco, "ValorProventoCota")
                or _texto_xml(bloco, "ValorRendimentoCota")
                or _texto_xml(bloco, "ValorAmortizacaoCota")
            )
            if not ticker or not data_pagamento or valor is None:
                continue
            eventos.append(
                {
                    "ticker": ticker,
                    "cnpj_fundo": cnpj_fundo,
                    "data_base": data_base,
                    "data_com": data_base,
                    "data_pagamento": data_pagamento,
                    "valor": valor,
                    "tipo": _normalizar_tipo_evento(bloco.tag),
                    "cod_isin": cod_isin,
                    "periodo_referencia": _limpar(_texto_xml(bloco, "PeriodoReferencia")),
                    "data_informacao": data_informacao,
                    "ato_societario_aprovacao": _normalizar_data(_texto_xml(bloco, "AtoSocietarioAprovacao")),
                    "rendimento_isento_ir": _limpar(_texto_xml(bloco, "RendimentoIsentoIR")),
                }
            )
    return eventos


def _dedupe_key(dados: dict[str, Any]) -> str:
    partes = [
        dados.get("ticker") or "",
        dados.get("cnpj_fundo") or "",
        dados.get("data_pagamento") or "",
        dados.get("data_base") or "",
        dados.get("data_com") or "",
        str(dados.get("valor") or ""),
        dados.get("protocolo") or "",
        dados.get("url_documento") or "",
    ]
    base = "|".join(str(parte).strip().lower() for parte in partes)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _ler_arquivo(caminho: Path) -> pd.DataFrame:
    if caminho.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(caminho, dtype=str)
    if caminho.suffix.lower() == ".json":
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return pd.DataFrame(dados if isinstance(dados, list) else dados.get("dados", []))
    try:
        return pd.read_csv(caminho, sep=None, engine="python", dtype=str, encoding="utf-8")
    except Exception:
        return pd.read_csv(caminho, sep=None, engine="python", dtype=str, encoding="latin1")


def _salvar_operacional(dados: dict[str, Any]) -> None:
    """Grava na tabela dividendos, sobrescrevendo fallback yfinance quando houver FNET."""
    if not dados.get("data_pagamento"):
        raise ValueError("data_pagamento é obrigatório para gravação operacional em dividendos.")

    db.executar(
        """
        DELETE FROM dividendos
        WHERE ticker = ?
          AND ABS(valor - ?) < 0.000001
          AND (
                data_pagamento = ?
             OR data_com = ?
             OR COALESCE(data_com, data_pagamento) = ?
          )
          AND COALESCE(fonte, '') <> 'FNET_AVISO_COTISTAS'
        """,
        (
            dados["ticker"],
            dados["valor"],
            dados["data_pagamento"],
            dados.get("data_com"),
            dados.get("data_com") or dados["data_pagamento"],
        ),
    )

    registro = {
        "ticker": dados["ticker"],
        "data_pagamento": dados["data_pagamento"],
        "valor": dados["valor"],
        "tipo": dados.get("tipo") or "INDEFINIDO",
        "fonte": "FNET_AVISO_COTISTAS",
        "data_base": dados.get("data_base"),
        "data_com": dados.get("data_com"),
        "protocolo": dados.get("protocolo"),
        "url_documento": dados.get("url_documento"),
    }
    db.executar("INSERT OR IGNORE INTO fiis (ticker, tipo, ativo) VALUES (?, 'FII', 1)", (dados["ticker"],))
    db.upsert("dividendos", registro)


def _salvar_fnet(dados: dict[str, Any]) -> None:
    dados = {
        **dados,
        "fonte": "FNET_AVISO_COTISTAS",
        "coletado_em": dados.get("coletado_em") or _agora_iso(),
    }
    dados["dedupe_key"] = _dedupe_key(dados)
    dados = {chave: valor for chave, valor in dados.items() if chave in _COLUNAS_TABELA}
    colunas_sql = ", ".join(dados.keys())
    placeholders = ", ".join("?" for _ in dados)
    updates = ", ".join(f"{col}=excluded.{col}" for col in dados if col != "dedupe_key")
    db.executar(
        f"""
        INSERT INTO {TABELA} ({colunas_sql})
        VALUES ({placeholders})
        ON CONFLICT(dedupe_key)
        DO UPDATE SET {updates}
        """,
        tuple(dados.values()),
    )
    _salvar_operacional(dados)


def importar_arquivo(caminho_arquivo: str | Path) -> dict[str, Any]:
    """Importa rendimentos de avisos aos cotistas a partir de CSV/Excel/JSON."""
    garantir_tabelas()
    caminho = Path(caminho_arquivo)

    try:
        df = _ler_arquivo(caminho)
        colunas = {campo: _localizar(df, campo) for campo in _ALIASES}

        if not colunas.get("ticker"):
            raise ValueError("Arquivo de dividendos FNET sem coluna de ticker identificável.")
        if not colunas.get("valor"):
            raise ValueError("Arquivo de dividendos FNET sem coluna de valor identificável.")

        total = 0
        ignorados = 0
        ignorados_sem_data_pagamento = 0
        coletado_em = _agora_iso()

        for _, row in df.iterrows():
            ticker = _limpar_ticker(row.get(colunas["ticker"])) if colunas.get("ticker") else None
            valor = _normalizar_float(row.get(colunas["valor"])) if colunas.get("valor") else None
            data_pagamento = _normalizar_data(row.get(colunas["data_pagamento"])) if colunas.get("data_pagamento") else None

            if not data_pagamento:
                ignorados += 1
                ignorados_sem_data_pagamento += 1
                continue
            if not ticker or valor is None:
                ignorados += 1
                continue

            dados = {
                "ticker": ticker,
                "cnpj_fundo": _limpar(row.get(colunas["cnpj_fundo"])) if colunas.get("cnpj_fundo") else None,
                "data_base": _normalizar_data(row.get(colunas["data_base"])) if colunas.get("data_base") else None,
                "data_com": _normalizar_data(row.get(colunas["data_com"])) if colunas.get("data_com") else None,
                "data_pagamento": data_pagamento,
                "valor": valor,
                "tipo": _limpar(row.get(colunas["tipo"])) if colunas.get("tipo") else "INDEFINIDO",
                "fonte": "FNET_AVISO_COTISTAS",
                "protocolo": _limpar(row.get(colunas["protocolo"])) if colunas.get("protocolo") else None,
                "url_documento": _limpar(row.get(colunas["url_documento"])) if colunas.get("url_documento") else None,
                "assunto": _limpar(row.get(colunas["assunto"])) if colunas.get("assunto") else None,
                "arquivo_origem": str(caminho),
                "coletado_em": coletado_em,
                "payload_json": row.to_json(force_ascii=False),
            }
            dados["dedupe_key"] = _dedupe_key(dados)
            _salvar_fnet(dados)
            total += 1

        tickers = sorted({str(t).upper().replace(".SA", "") for t in df[colunas["ticker"]].dropna()}) if colunas.get("ticker") else []
        for ticker in tickers:
            classificar_dividendos(ticker)

        resumo = {
            "arquivo": str(caminho),
            "registros": total,
            "ignorados": ignorados,
            "ignorados_sem_data_pagamento": ignorados_sem_data_pagamento,
            "tickers": tickers,
        }
        observabilidade.registrar_evento(
            "INFO",
            "coleta.fnet_dividendos",
            "Dividendos FNET importados como fonte primária",
            fonte="FNET_AVISO_COTISTAS",
            contexto=resumo,
        )
        return resumo

    except Exception as erro:
        observabilidade.registrar_erro(
            "coleta.fnet_dividendos",
            erro,
            fonte="FNET_AVISO_COTISTAS",
            contexto={"arquivo": str(caminho)},
        )
        return {"arquivo": str(caminho), "erro": str(erro), "registros": 0}


def _cnpj_limpo(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj or "")


def buscar_documentos_online(
    cnpj_fundo: str,
    limite: int = 120,
    apenas_do_dia: bool = False,
    verify_ssl: bool = True,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Busca metadados FNET por CNPJ. O filtro final ocorre no XML baixado."""
    limite = 10 if apenas_do_dia else limite
    params = {
        "d": 1,
        "s": offset,
        "l": limite,
        "tipoFundo": "1",
        "idCategoriaDocumento": "0",
        "idTipoDocumento": "0",
        "idEspecieDocumento": "0",
        "paginaCertificados": "false",
        "cnpj": _cnpj_limpo(cnpj_fundo),
        "cnpjFundo": _cnpj_limpo(cnpj_fundo),
    }
    try:
        resposta = _session.get(_FNET_GRID, params=params, headers=_HEADERS, timeout=_TIMEOUT, verify=verify_ssl)
        if resposta.status_code != 200:
            return []
        dados = resposta.json()
    except Exception:
        return []
    return list(dados.get("data") or [])


def _eh_metadado_provento(doc: dict[str, Any]) -> bool:
    texto = " ".join(
        str(doc.get(chave) or "")
        for chave in ("categoriaDocumento", "tipoDocumento", "especieDocumento", "assuntos")
    ).upper()
    return "AVISO AOS COTISTAS" in texto and "RENDIMENTOS" in texto and "AMORTIZA" in texto


def descobrir_documentos_proventos(
    cnpj_fundo: str,
    tamanho_lote: int = 80,
    max_paginas: int = 10,
    verify_ssl: bool = True,
) -> list[dict[str, Any]]:
    """Pagina o grid FNET e retorna candidatos rotulados como rendimentos/amortizacoes."""
    encontrados: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for pagina in range(max_paginas):
        offset = pagina * tamanho_lote
        docs = buscar_documentos_online(cnpj_fundo, limite=tamanho_lote, offset=offset, verify_ssl=verify_ssl)
        if not docs:
            break
        for doc in docs:
            doc_id = str(doc.get("id") or "")
            if doc_id and doc_id not in vistos and _eh_metadado_provento(doc):
                vistos.add(doc_id)
                encontrados.append(doc)
        if len(docs) < tamanho_lote:
            break
    return encontrados


def baixar_xml_documento(doc_id: str | int, verify_ssl: bool = True) -> bytes | None:
    resposta = _session.get(_FNET_DOWNLOAD.format(doc_id=doc_id), headers=_HEADERS, timeout=_TIMEOUT, verify=verify_ssl)
    if resposta.status_code != 200:
        return None
    conteudo = _decodificar_resposta_fnet(resposta.content)
    if not conteudo.startswith(b"<?xml") and not conteudo.startswith(b"<"):
        return None
    return conteudo


def importar_online(
    cnpj_fundo: str,
    limite: int = 120,
    apenas_do_dia: bool = False,
    verify_ssl: bool = True,
    max_paginas: int = 10,
) -> dict[str, Any]:
    """Importa dividendos oficiais FNET baixando XMLs estruturados por CNPJ."""
    garantir_tabelas()
    documentos = (
        buscar_documentos_online(
            cnpj_fundo,
            limite=limite,
            apenas_do_dia=apenas_do_dia,
            verify_ssl=verify_ssl,
        )
        if apenas_do_dia
        else descobrir_documentos_proventos(
            cnpj_fundo,
            tamanho_lote=limite,
            max_paginas=max_paginas,
            verify_ssl=verify_ssl,
        )
    )
    total = 0
    documentos_com_evento = 0
    erros = 0
    tickers: set[str] = set()
    coletado_em = _agora_iso()

    for doc in documentos:
        doc_id = doc.get("id")
        if not doc_id:
            continue
        try:
            xml = baixar_xml_documento(doc_id, verify_ssl=verify_ssl)
            if not xml:
                continue
            eventos = extrair_eventos_xml(xml)
            if not eventos:
                continue
            documentos_com_evento += 1
            for evento in eventos:
                ticker = evento.get("ticker")
                if ticker:
                    tickers.add(ticker)
                payload = {
                    **evento,
                    "protocolo": str(doc_id),
                    "url_documento": _FNET_VISUALIZAR.format(doc_id=doc_id),
                    "assunto": doc.get("tipoDescricao") or doc.get("especieDocumento") or "Rendimentos e Amortizacoes",
                    "arquivo_origem": "FNET_API_XML",
                    "coletado_em": coletado_em,
                    "payload_json": json.dumps({"documento": doc, "evento": evento}, ensure_ascii=False),
                }
                _salvar_fnet(payload)
                total += 1
        except Exception as erro:
            erros += 1
            observabilidade.registrar_erro(
                "coleta.fnet_dividendos.online.documento",
                erro,
                fonte="FNET_AVISO_COTISTAS",
                contexto={"doc_id": doc_id, "cnpj_fundo": cnpj_fundo},
            )

    for ticker in tickers:
        classificar_dividendos(ticker)

    resumo = {
        "cnpj_fundo": cnpj_fundo,
        "documentos_analisados": len(documentos),
        "documentos_com_evento": documentos_com_evento,
        "registros": total,
        "erros": erros,
        "tickers": sorted(tickers),
    }
    observabilidade.registrar_evento(
        "INFO",
        "coleta.fnet_dividendos.online",
        "Dividendos FNET online importados",
        fonte="FNET_AVISO_COTISTAS",
        contexto=resumo,
    )
    return resumo


def importar_documento_online(
    doc_id: str | int,
    metadados: dict[str, Any] | None = None,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    """Importa um XML FNET estruturado pelo id do documento."""
    garantir_tabelas()
    metadados = metadados or {}
    xml = baixar_xml_documento(doc_id, verify_ssl=verify_ssl)
    if not xml:
        return {"doc_id": str(doc_id), "registros": 0, "erro": "Documento nao retornou XML estruturado."}

    eventos = extrair_eventos_xml(xml)
    tickers: set[str] = set()
    coletado_em = _agora_iso()
    total = 0

    for evento in eventos:
        ticker = evento.get("ticker")
        if ticker:
            tickers.add(ticker)
        payload = {
            **evento,
            "protocolo": str(doc_id),
            "url_documento": _FNET_VISUALIZAR.format(doc_id=doc_id),
            "assunto": metadados.get("tipoDescricao") or metadados.get("especieDocumento") or "Rendimentos e Amortizacoes",
            "arquivo_origem": "FNET_API_XML",
            "coletado_em": coletado_em,
            "payload_json": json.dumps({"documento": metadados, "evento": evento}, ensure_ascii=False),
        }
        _salvar_fnet(payload)
        total += 1

    for ticker in tickers:
        classificar_dividendos(ticker)

    return {"doc_id": str(doc_id), "registros": total, "tickers": sorted(tickers)}


def cobertura_fnet(ticker: str) -> dict[str, Any]:
    garantir_tabelas()
    ticker_norm = ticker.upper().replace(".SA", "")
    row = db.buscar_um(
        """
        SELECT COUNT(*) AS qtd, MIN(data_pagamento) AS inicio, MAX(data_pagamento) AS fim
        FROM dividendos
        WHERE ticker = ? AND fonte = 'FNET_AVISO_COTISTAS'
        """,
        (ticker_norm,),
    )
    return {
        "ticker": ticker_norm,
        "fonte_primaria": "FNET_AVISO_COTISTAS",
        "qtd": int(row["qtd"] or 0) if row else 0,
        "inicio": row["inicio"] if row else None,
        "fim": row["fim"] if row else None,
        "tem_fnet": bool(row and row["qtd"]),
    }
