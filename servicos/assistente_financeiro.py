"""
servicos/assistente_financeiro.py

Camada de uso diario do FIIA:
- detalhe consolidado por fundo;
- alertas operacionais;
- evolucao entre snapshots/decisoes;
- sugestao de rebalanceamento;
- exportacao offline em texto/PDF.

As consultas sao auditaveis e nao executam scraping nem motor de decisao.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from banco import db
from carteira import repositorio_carteira
from carteira.politica_carteira import avaliar_alocacao_sugerida
from decisao.persistencia_decisao import ultima_decisao, historico
from coleta import cvm_fnet_documentos


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row else {}


def _ticker(ticker: str) -> str:
    return ticker.upper().replace(".SA", "").strip()


def _json(valor: Any, padrao: Any) -> Any:
    if isinstance(valor, (dict, list)):
        return valor
    if not valor:
        return padrao
    try:
        return json.loads(valor)
    except Exception:
        return padrao


def _ultimo_indicador(ticker: str) -> dict[str, Any]:
    row = db.buscar_um(
        "SELECT * FROM indicadores WHERE ticker = ? ORDER BY data DESC, coletado_em DESC LIMIT 1",
        (_ticker(ticker),),
    )
    return _row_dict(row)


def _indicador_anterior(ticker: str, data_atual: str | None) -> dict[str, Any]:
    if not data_atual:
        return {}
    row = db.buscar_um(
        """
        SELECT * FROM indicadores
        WHERE ticker = ? AND data < ?
        ORDER BY data DESC, coletado_em DESC
        LIMIT 1
        """,
        (_ticker(ticker), data_atual),
    )
    return _row_dict(row)


def _ultimo_dividendo(ticker: str) -> dict[str, Any] | None:
    row = db.buscar_um(
        """
        SELECT ticker, data_pagamento, data_base, data_com, valor, tipo, fonte, protocolo, url_documento
        FROM dividendos
        WHERE ticker = ?
        ORDER BY data_pagamento DESC
        LIMIT 1
        """,
        (_ticker(ticker),),
    )
    return _row_dict(row) if row else None


def _ultimo_trimestral(ticker: str) -> dict[str, Any]:
    row = db.buscar_um(
        """
        SELECT data_referencia, COUNT(*) as quantidade_imoveis,
               AVG(vacancia_pct) as vacancia_media_simples,
               SUM(COALESCE(vacancia_pct, 0) * COALESCE(area, 1)) / NULLIF(SUM(COALESCE(area, 1)), 0) as vacancia_media_ponderada,
               MAX(inadimplencia_pct) as maior_inadimplencia,
               MAX(receita_pct) as maior_receita_imovel
        FROM inf_trimestral_imoveis
        WHERE ticker = ?
          AND data_referencia = (
              SELECT MAX(data_referencia) FROM inf_trimestral_imoveis WHERE ticker = ?
          )
        GROUP BY data_referencia
        """,
        (_ticker(ticker), _ticker(ticker)),
    )
    return _row_dict(row)


def _cobertura_fnet(ticker: str) -> dict[str, Any]:
    docs = cvm_fnet_documentos.listar_por_ticker(_ticker(ticker), limite=20)
    tipos = sorted({str(doc.get("tipo_documento") or doc.get("categoria") or "NAO_CLASSIFICADO") for doc in docs})
    ultimo = docs[0] if docs else None
    row_cache = db.buscar_um(
        "SELECT doc_id, data_doc, coletado_em, LENGTH(texto) as caracteres FROM relatorios_cache WHERE ticker = ?",
        (_ticker(ticker),),
    )
    return {
        "quantidade_documentos": len(docs),
        "tipos": tipos,
        "ultimo_documento": ultimo,
        "relatorio_cache": _row_dict(row_cache),
    }


def detalhe_fundo(ticker: str) -> dict[str, Any]:
    ticker_norm = _ticker(ticker)
    ind = _ultimo_indicador(ticker_norm)
    dec = ultima_decisao(ticker_norm) or {}
    payload = _json(dec.get("payload_json"), {})
    posicao = repositorio_carteira.obter_posicao(ticker_norm)
    trimestral = _ultimo_trimestral(ticker_norm)
    div = _ultimo_dividendo(ticker_norm)
    fnet = _cobertura_fnet(ticker_norm)

    return {
        "status": "ok",
        "ticker": ticker_norm,
        "indicador": ind,
        "decisao": dec,
        "payload_decisao": payload,
        "posicao": posicao,
        "ultimo_dividendo": div,
        "trimestral": trimestral,
        "fnet": fnet,
        "sem_scraping": True,
        "executou_motor": False,
    }


def _garantir_tabela_alertas() -> None:
    db.executar(
        """
        CREATE TABLE IF NOT EXISTS assistente_alertas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            tipo TEXT NOT NULL,
            severidade TEXT NOT NULL,
            mensagem TEXT NOT NULL,
            data_referencia TEXT NOT NULL,
            payload_json TEXT,
            criado_em TEXT NOT NULL,
            UNIQUE(ticker, tipo, data_referencia)
        )
        """
    )


def _salvar_alerta(alerta: dict[str, Any]) -> None:
    _garantir_tabela_alertas()
    db.executar(
        """
        INSERT INTO assistente_alertas
            (ticker, tipo, severidade, mensagem, data_referencia, payload_json, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, tipo, data_referencia)
        DO UPDATE SET
            severidade = excluded.severidade,
            mensagem = excluded.mensagem,
            payload_json = excluded.payload_json,
            criado_em = excluded.criado_em
        """,
        (
            alerta["ticker"],
            alerta["tipo"],
            alerta["severidade"],
            alerta["mensagem"],
            alerta["data_referencia"],
            json.dumps(alerta.get("payload") or {}, ensure_ascii=False, default=str),
            _agora_iso(),
        ),
    )


def listar_alertas_novos(desde_id: int = 0, limite: int = 20) -> dict[str, Any]:
    """
    Consulta alertas ja persistidos sem gerar novos registros.

    Usado pela PWA para polling leve. Nao chama gerar_alertas(), nao executa
    motor e nao aciona scraping.
    """
    _garantir_tabela_alertas()
    desde = max(0, int(desde_id or 0))
    limite_seguro = min(max(int(limite or 20), 1), 100)
    rows = db.buscar_todos(
        """
        SELECT id, ticker, tipo, severidade, mensagem, data_referencia, payload_json, criado_em
        FROM assistente_alertas
        WHERE id > ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (desde, limite_seguro),
    )
    alertas = []
    for row in rows:
        item = dict(row)
        item["payload"] = _json(item.pop("payload_json", None), {})
        alertas.append(item)
    ultimo_id = max([desde] + [int(a["id"]) for a in alertas])
    return {
        "status": "ok",
        "quantidade": len(alertas),
        "ultimo_id": ultimo_id,
        "alertas": alertas,
        "sem_scraping": True,
        "executou_motor": False,
        "gerou_alertas": False,
    }


def gerar_alertas(tickers: list[str] | None = None) -> dict[str, Any]:
    if tickers:
        universo = [_ticker(t) for t in tickers if _ticker(t)]
    else:
        rows = db.buscar_todos(
            """
            SELECT ticker FROM carteira_posicoes WHERE quantidade > 0
            UNION
            SELECT ticker FROM decisoes WHERE data_decisao >= date('now', '-45 day')
            """
        )
        universo = sorted({_ticker(row["ticker"]) for row in rows})

    alertas: list[dict[str, Any]] = []
    hoje = date.today().isoformat()

    for ticker in universo:
        ind = _ultimo_indicador(ticker)
        dec = ultima_decisao(ticker) or {}
        if not ind and not dec:
            continue

        preco = ind.get("preco") or dec.get("preco_na_decisao")
        entrada = dec.get("preco_entrada") or dec.get("preco_teto")
        decisao = str(dec.get("decisao") or "").upper()
        if preco and entrada and float(preco) <= float(entrada) and decisao in {"COMPRAR", "COMPRAR_PARCIAL", "COMPRAR_PARCIALMENTE", "MONITORAR"}:
            alertas.append({
                "ticker": ticker,
                "tipo": "ZONA_ENTRADA",
                "severidade": "ALTA" if decisao.startswith("COMPRAR") else "MEDIA",
                "mensagem": f"{ticker} entrou na zona de entrada: preco {float(preco):.2f} <= teto {float(entrada):.2f}.",
                "data_referencia": hoje,
                "payload": {"preco": preco, "preco_entrada": entrada, "decisao": decisao},
            })

        div = _ultimo_dividendo(ticker)
        if not div:
            alertas.append({
                "ticker": ticker,
                "tipo": "DIVIDENDO_AUSENTE",
                "severidade": "MEDIA",
                "mensagem": f"{ticker} sem dividendo recente persistido.",
                "data_referencia": hoje,
                "payload": {},
            })

        trimestral = _ultimo_trimestral(ticker)
        if not trimestral:
            alertas.append({
                "ticker": ticker,
                "tipo": "VACANCIA_TRIMESTRAL_AUSENTE",
                "severidade": "MEDIA",
                "mensagem": f"{ticker} sem vacancia oficial trimestral persistida.",
                "data_referencia": hoje,
                "payload": {},
            })

    for alerta in alertas:
        _salvar_alerta(alerta)

    return {"status": "ok", "quantidade": len(alertas), "alertas": alertas, "sem_scraping": True, "executou_motor": False}


def _quebrar_linhas_pdf(texto: str, largura: int = 92) -> list[str]:
    linhas: list[str] = []
    for bruto in str(texto or "").splitlines():
        palavras = bruto.split()
        if not palavras:
            linhas.append("")
            continue
        atual = ""
        for palavra in palavras:
            candidato = f"{atual} {palavra}".strip()
            if len(candidato) <= largura:
                atual = candidato
                continue
            if atual:
                linhas.append(atual)
            atual = palavra[:largura]
        linhas.append(atual)
    return linhas


def _escapar_pdf(texto: str) -> str:
    return str(texto).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_simples(texto: str) -> bytes:
    linhas = _quebrar_linhas_pdf(texto)
    paginas = [linhas[i:i + 45] for i in range(0, len(linhas), 45)] or [[]]
    objetos: list[str] = ["<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + i * 2} 0 R" for i in range(len(paginas)))
    objetos.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(paginas)} >>")
    for indice, pagina in enumerate(paginas):
        pagina_obj = 3 + indice * 2
        conteudo_obj = pagina_obj + 1
        objetos.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> /Contents {conteudo_obj} 0 R >>")
        comandos = ["BT", "/F1 10 Tf", "50 800 Td", "14 TL"]
        for linha in pagina:
            seguro = _escapar_pdf(linha.encode("latin-1", "replace").decode("latin-1"))
            comandos.append(f"({seguro}) Tj")
            comandos.append("T*")
        comandos.append("ET")
        stream = "\n".join(comandos)
        objetos.append(f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream")

    saida = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for numero, objeto in enumerate(objetos, start=1):
        offsets.append(len(saida))
        saida.extend(f"{numero} 0 obj\n{objeto}\nendobj\n".encode("latin-1"))
    xref = len(saida)
    saida.extend(f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode("latin-1"))
    for offset in offsets[1:]:
        saida.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    saida.extend(f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("latin-1"))
    return bytes(saida)


def gerar_pdf_simples(texto: str) -> bytes:
    return _pdf_simples(texto)


def _delta(atual: Any, anterior: Any) -> dict[str, Any]:
    if atual is None or anterior is None:
        return {"atual": atual, "anterior": anterior, "delta": None, "direcao": "INDISPONIVEL"}
    try:
        delta = float(atual) - float(anterior)
    except Exception:
        return {"atual": atual, "anterior": anterior, "delta": None, "direcao": "INDISPONIVEL"}
    direcao = "ESTAVEL"
    if delta > 0:
        direcao = "SUBIU"
    elif delta < 0:
        direcao = "CAIU"
    return {"atual": atual, "anterior": anterior, "delta": round(delta, 4), "direcao": direcao}


def evolucao_fundo(ticker: str) -> dict[str, Any]:
    ticker_norm = _ticker(ticker)
    atual = _ultimo_indicador(ticker_norm)
    anterior = _indicador_anterior(ticker_norm, atual.get("data"))
    decisoes = historico(ticker_norm, limite=2)
    dec_atual = decisoes[0] if decisoes else {}
    dec_anterior = decisoes[1] if len(decisoes) > 1 else {}

    metricas = {
        "preco": _delta(atual.get("preco"), anterior.get("preco")),
        "pvp": _delta(atual.get("pvp"), anterior.get("pvp")),
        "dy_12m": _delta(atual.get("dy_12m"), anterior.get("dy_12m")),
        "vacancia_fisica": _delta(atual.get("vacancia_fisica"), anterior.get("vacancia_fisica")),
        "confiabilidade": _delta(atual.get("confiabilidade"), anterior.get("confiabilidade")),
    }

    pontos = 0
    if (metricas["confiabilidade"]["delta"] or 0) > 0:
        pontos += 1
    if (metricas["vacancia_fisica"]["delta"] or 0) < 0:
        pontos += 1
    if str(dec_atual.get("decisao") or "") != str(dec_anterior.get("decisao") or ""):
        pontos += 1 if str(dec_atual.get("decisao") or "").startswith("COMPRAR") else -1

    leitura = "ESTAVEL"
    if pontos > 0:
        leitura = "MELHOROU"
    elif pontos < 0:
        leitura = "PIOROU"

    return {
        "status": "ok",
        "ticker": ticker_norm,
        "leitura": leitura,
        "indicador_atual": atual,
        "indicador_anterior": anterior,
        "metricas": metricas,
        "decisao_atual": dec_atual,
        "decisao_anterior": dec_anterior,
        "sem_scraping": True,
        "executou_motor": False,
    }


def rebalanceamento() -> dict[str, Any]:
    posicoes = repositorio_carteira.listar_posicoes()
    valores = []
    total = 0.0
    for pos in posicoes:
        ind = _ultimo_indicador(pos["ticker"])
        preco = float(ind.get("preco") or pos.get("preco_medio") or 0.0)
        valor = float(pos.get("quantidade") or 0.0) * preco
        total += valor
        valores.append((pos, ind, valor))

    por_segmento: dict[str, float] = {}
    for pos, ind, valor in valores:
        segmento = pos.get("segmento") or ind.get("segmento") or "INDEFINIDO"
        por_segmento[segmento] = por_segmento.get(segmento, 0.0) + valor

    sugestoes = []
    for pos, ind, valor in valores:
        ticker = pos["ticker"]
        dec = ultima_decisao(ticker) or {"ticker": ticker, "decisao": "MONITORAR"}
        segmento = pos.get("segmento") or ind.get("segmento") or dec.get("segmento")
        pct_ativo = valor / total if total else 0.0
        pct_segmento = por_segmento.get(segmento or "INDEFINIDO", 0.0) / total if total else 0.0
        politica = avaliar_alocacao_sugerida(
            ticker=ticker,
            decisao=dec.get("decisao") or "MONITORAR",
            risco=dec.get("risco"),
            confianca=dec.get("confianca"),
            segmento=segmento,
            fonte_patrimonial=dec.get("fonte_patrimonial"),
            percentual_atual_ativo=pct_ativo,
            percentual_atual_segmento=pct_segmento,
            caixa_disponivel_pct=1.0,
        ).to_dict()
        sugestoes.append({
            "ticker": ticker,
            "valor_atual": round(valor, 2),
            "percentual_atual": round(pct_ativo, 4),
            "segmento": segmento,
            "decisao": dec.get("decisao"),
            "politica": politica,
        })

    return {
        "status": "ok",
        "valor_total_estimado": round(total, 2),
        "quantidade": len(sugestoes),
        "sugestoes": sugestoes,
        "sem_scraping": True,
        "executou_motor": False,
    }


def relatorio_offline(ticker: str, formato: str = "txt") -> dict[str, Any]:
    detalhe = detalhe_fundo(ticker)
    evolucao = evolucao_fundo(ticker)
    alertas = gerar_alertas([ticker]).get("alertas", [])
    ind = detalhe.get("indicador") or {}
    dec = detalhe.get("decisao") or {}
    tri = detalhe.get("trimestral") or {}
    div = detalhe.get("ultimo_dividendo") or {}
    fnet = detalhe.get("fnet") or {}

    linhas = [
        f"FIIA - Relatorio offline: {detalhe['ticker']}",
        "=" * 56,
        f"Decisao: {dec.get('decisao', 'NAO_DISPONIVEL')} | Confianca: {dec.get('confianca', 'NAO_DISPONIVEL')}",
        f"Preco atual: {ind.get('preco', 'NAO_DISPONIVEL')} | P/VP: {ind.get('pvp', 'NAO_DISPONIVEL')} | DY 12M: {ind.get('dy_12m', 'NAO_DISPONIVEL')}",
        f"Ultimo dividendo: {div.get('valor', 'NAO_DISPONIVEL')} em {div.get('data_pagamento', 'NAO_DISPONIVEL')}",
        f"Vacancia trimestral: {tri.get('vacancia_media_ponderada', 'NAO_DISPONIVEL')} | Imoveis: {tri.get('quantidade_imoveis', 'NAO_DISPONIVEL')}",
        f"FNET documentos: {fnet.get('quantidade_documentos', 0)} | Tipos: {', '.join(fnet.get('tipos') or []) or 'NAO_DISPONIVEL'}",
        f"Evolucao: {evolucao.get('leitura')}",
        "",
        "Alertas:",
    ]
    linhas.extend([f"- {a['mensagem']}" for a in alertas] or ["- Sem alertas operacionais."])
    linhas.extend(["", "Motivo da decisao:", str(dec.get("motivo") or "NAO_DISPONIVEL")])

    conteudo = "\n".join(linhas)
    formato_norm = str(formato or "txt").lower()
    if formato_norm == "pdf":
        return {
            "status": "ok",
            "ticker": detalhe["ticker"],
            "formato": "pdf",
            "conteudo": _pdf_simples(conteudo),
            "content_type": "application/pdf",
            "sem_scraping": True,
            "executou_motor": False,
        }
    return {
        "status": "ok",
        "ticker": detalhe["ticker"],
        "formato": "txt" if formato_norm not in {"md", "markdown"} else "md",
        "conteudo": conteudo,
        "content_type": "text/plain; charset=utf-8",
        "sem_scraping": True,
        "executou_motor": False,
    }
