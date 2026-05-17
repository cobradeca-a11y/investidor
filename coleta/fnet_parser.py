"""
coleta/fnet_parser.py
Pipeline FNET → parser → Gemini → score documental.

Fluxo:
1. lê documentos em cvm_fnet_documentos_fii;
2. baixa URL FNET;
3. extrai texto simples de HTML/TXT/PDF quando possível;
4. envia texto para processamento.nlp_fnet.classificar_documento_com_ia;
5. grava resultado em fnet_documentos_processados;
6. consolida score por ticker em fnet_score_documental.

Observação:
- PDF depende de pypdf quando disponível;
- quando extração real falha, usa metadados como fallback seguro.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import datetime, timezone
from typing import Any

import requests

from banco import db
from processamento.nlp_fnet import classificar_documento_com_ia
from sistema import observabilidade

HEADERS = {"User-Agent": "FIIA/1.0"}

TABELA_PROCESSADOS = "fnet_documentos_processados"
TABELA_SCORE = "fnet_score_documental"


_NIVEL_PESO = {
    "BAIXO": 0,
    "MEDIO": 2,
    "MÉDIO": 2,
    "ALTO": 5,
    "INDEFINIDO": 1,
}


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_texto(texto: str) -> str:
    return hashlib.sha256((texto or "").encode("utf-8", errors="ignore")).hexdigest()


def garantir_tabelas() -> None:
    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA_PROCESSADOS} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento_fnet_id INTEGER,
            ticker TEXT,
            cnpj_fundo TEXT,
            protocolo TEXT,
            url_documento TEXT,
            assunto TEXT,
            tipo_documento TEXT,
            categoria TEXT,
            texto_extraido TEXT,
            texto_hash TEXT NOT NULL UNIQUE,
            nivel TEXT,
            motivo TEXT,
            termos_detectados TEXT,
            fonte_classificacao TEXT,
            modelo TEXT,
            processado_em TEXT NOT NULL,
            payload_json TEXT
        )
        """
    )
    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA_SCORE} (
            ticker TEXT PRIMARY KEY,
            score_documental REAL NOT NULL,
            nivel_maximo TEXT,
            qtd_documentos INTEGER NOT NULL,
            qtd_alto INTEGER NOT NULL DEFAULT 0,
            qtd_medio INTEGER NOT NULL DEFAULT 0,
            qtd_baixo INTEGER NOT NULL DEFAULT 0,
            atualizado_em TEXT NOT NULL,
            payload_json TEXT
        )
        """
    )


def _normalizar_html(html: str) -> str:
    texto = re.sub(r"(?is)<script.*?</script>", " ", html)
    texto = re.sub(r"(?is)<style.*?</style>", " ", texto)
    texto = re.sub(r"(?s)<[^>]+>", " ", texto)
    texto = re.sub(r"&nbsp;", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _extrair_pdf(conteudo: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return ""

    try:
        reader = PdfReader(io.BytesIO(conteudo))
        partes: list[str] = []
        for page in reader.pages[:20]:
            try:
                partes.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(partes).strip()
    except Exception:
        return ""


def baixar_e_extrair_texto(url: str) -> dict[str, Any]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        content_type = (resp.headers.get("content-type") or "").lower()
        conteudo = resp.content

        if "pdf" in content_type or conteudo[:4] == b"%PDF":
            texto = _extrair_pdf(conteudo)
            return {"texto": texto, "content_type": content_type or "application/pdf", "metodo": "pdf_pypdf" if texto else "pdf_sem_texto"}

        try:
            texto_bruto = conteudo.decode(resp.encoding or "utf-8", errors="ignore")
        except Exception:
            texto_bruto = conteudo.decode("latin-1", errors="ignore")

        if "html" in content_type or "<html" in texto_bruto[:500].lower():
            return {"texto": _normalizar_html(texto_bruto), "content_type": content_type, "metodo": "html_regex"}

        return {"texto": re.sub(r"\s+", " ", texto_bruto).strip(), "content_type": content_type, "metodo": "texto_bruto"}
    except Exception as erro:
        observabilidade.registrar_erro("coleta.fnet_parser.baixar_e_extrair_texto", erro, contexto={"url": url})
        return {"texto": "", "content_type": None, "metodo": "erro_download", "erro": str(erro)}


def _ticker_por_cnpj(cnpj_fundo: str | None) -> str | None:
    if not cnpj_fundo:
        return None
    row = db.buscar_um(
        """
        SELECT ticker_b3_11
        FROM cadastro_fundos_master
        WHERE REPLACE(REPLACE(REPLACE(cnpj_fundo,'.',''),'/',''),'-','') = ?
           OR REPLACE(REPLACE(REPLACE(cnpj_classe,'.',''),'/',''),'-','') = ?
        LIMIT 1
        """,
        (cnpj_fundo, cnpj_fundo),
    )
    return row["ticker_b3_11"] if row else None


def documentos_pendentes(limite: int = 50) -> list[dict[str, Any]]:
    garantir_tabelas()
    rows = db.buscar_todos(
        """
        SELECT d.*
        FROM cvm_fnet_documentos_fii d
        LEFT JOIN fnet_documentos_processados p
          ON p.url_documento = d.url_documento
        WHERE d.url_documento IS NOT NULL
          AND d.url_documento != ''
          AND p.id IS NULL
        ORDER BY d.id DESC
        LIMIT ?
        """,
        (limite,),
    )
    return [dict(r) for r in rows]


def processar_documento(row: dict[str, Any]) -> dict[str, Any]:
    garantir_tabelas()

    url = row.get("url_documento")
    assunto = row.get("assunto") or row.get("tipo_documento") or row.get("categoria") or "Documento FNET"
    cnpj = row.get("cnpj_fundo")
    ticker = row.get("ticker") or _ticker_por_cnpj(cnpj)

    extracao = baixar_e_extrair_texto(url) if url else {"texto": "", "metodo": "sem_url"}
    texto = (extracao.get("texto") or "").strip()

    if len(texto) < 80:
        texto = "\n".join(
            str(x or "")
            for x in [assunto, row.get("categoria"), row.get("tipo_documento"), row.get("protocolo"), url]
        ).strip()

    texto_hash = _hash_texto(f"{url}\n{assunto}\n{texto[:12000]}")
    resultado = classificar_documento_com_ia(
        texto_documento=texto,
        assunto=assunto,
        ticker=ticker,
        documento_id=row.get("id") or row.get("protocolo"),
    )

    payload = {
        "documento": row,
        "extracao": {k: v for k, v in extracao.items() if k != "texto"},
        "classificacao": resultado,
    }

    db.executar(
        f"""
        INSERT INTO {TABELA_PROCESSADOS}
            (documento_fnet_id, ticker, cnpj_fundo, protocolo, url_documento, assunto,
             tipo_documento, categoria, texto_extraido, texto_hash, nivel, motivo,
             termos_detectados, fonte_classificacao, modelo, processado_em, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(texto_hash)
        DO UPDATE SET
            ticker=excluded.ticker,
            nivel=excluded.nivel,
            motivo=excluded.motivo,
            termos_detectados=excluded.termos_detectados,
            fonte_classificacao=excluded.fonte_classificacao,
            modelo=excluded.modelo,
            processado_em=excluded.processado_em,
            payload_json=excluded.payload_json
        """,
        (
            row.get("id"),
            ticker,
            cnpj,
            row.get("protocolo"),
            url,
            assunto,
            row.get("tipo_documento"),
            row.get("categoria"),
            texto[:20000],
            texto_hash,
            resultado.get("nivel"),
            resultado.get("motivo"),
            json.dumps(resultado.get("termos_detectados", []), ensure_ascii=False),
            resultado.get("fonte_classificacao"),
            resultado.get("modelo"),
            _agora_iso(),
            json.dumps(payload, ensure_ascii=False, default=str),
        ),
    )

    return {"ticker": ticker, "url": url, "nivel": resultado.get("nivel"), "motivo": resultado.get("motivo")}


def consolidar_score_documental() -> dict[str, Any]:
    garantir_tabelas()
    rows = db.buscar_todos(
        f"""
        SELECT ticker, nivel, motivo, url_documento
        FROM {TABELA_PROCESSADOS}
        WHERE ticker IS NOT NULL
        """
    )

    por_ticker: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        por_ticker.setdefault(r["ticker"], []).append(dict(r))

    atualizados = 0
    for ticker, docs in por_ticker.items():
        pesos = [_NIVEL_PESO.get((d.get("nivel") or "INDEFINIDO").upper(), 1) for d in docs]
        penalidade = min(40, sum(pesos))
        score = max(0, 100 - penalidade)
        niveis = [(d.get("nivel") or "INDEFINIDO").upper() for d in docs]
        nivel_maximo = "ALTO" if "ALTO" in niveis else "MEDIO" if "MEDIO" in niveis or "MÉDIO" in niveis else "BAIXO" if "BAIXO" in niveis else "INDEFINIDO"
        payload = {
            "documentos": docs[-20:],
            "penalidade": penalidade,
            "regra": "100 - soma_pesos_documentais_com_teto_40",
        }
        db.executar(
            f"""
            INSERT INTO {TABELA_SCORE}
                (ticker, score_documental, nivel_maximo, qtd_documentos, qtd_alto, qtd_medio, qtd_baixo, atualizado_em, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker)
            DO UPDATE SET
                score_documental=excluded.score_documental,
                nivel_maximo=excluded.nivel_maximo,
                qtd_documentos=excluded.qtd_documentos,
                qtd_alto=excluded.qtd_alto,
                qtd_medio=excluded.qtd_medio,
                qtd_baixo=excluded.qtd_baixo,
                atualizado_em=excluded.atualizado_em,
                payload_json=excluded.payload_json
            """,
            (
                ticker,
                score,
                nivel_maximo,
                len(docs),
                niveis.count("ALTO"),
                niveis.count("MEDIO") + niveis.count("MÉDIO"),
                niveis.count("BAIXO"),
                _agora_iso(),
                json.dumps(payload, ensure_ascii=False, default=str),
            ),
        )
        atualizados += 1

    return {"tickers_atualizados": atualizados, "documentos_considerados": len(rows)}


def processar_pendentes(limite: int = 20) -> dict[str, Any]:
    garantir_tabelas()
    pendentes = documentos_pendentes(limite=limite)
    resultados: list[dict[str, Any]] = []
    erros = 0

    for row in pendentes:
        try:
            resultados.append(processar_documento(row))
        except Exception as erro:
            erros += 1
            observabilidade.registrar_erro("coleta.fnet_parser.processar_pendentes", erro, contexto={"documento": row})

    score = consolidar_score_documental()
    return {
        "pendentes_lidos": len(pendentes),
        "processados": len(resultados),
        "erros": erros,
        "score": score,
        "amostra": resultados[:5],
    }


def score_documental_ticker(ticker: str) -> dict[str, Any] | None:
    garantir_tabelas()
    row = db.buscar_um(f"SELECT * FROM {TABELA_SCORE} WHERE ticker = ?", (ticker.upper(),))
    return dict(row) if row else None


if __name__ == "__main__":
    print(processar_pendentes(limite=10))
