"""
relatorios/relatorios_auditaveis.py

Relatórios técnicos auditáveis do FIIA.

Contratos:
- não altera decisão;
- não aciona scraping;
- não chama motor decisório;
- usa decisões persistidas e auditoria/replay existentes;
- campos ausentes são representados como "não disponível".
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from banco import db
from decisao.auditoria_decisao import consultar_decisao_auditavel, listar_decisoes_auditaveis

NAO_DISPONIVEL = "não disponível"
VERSAO_RELATORIO = "relatorio-auditavel-v1"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nd(valor: Any) -> Any:
    if valor is None or valor == "":
        return NAO_DISPONIVEL
    return valor


def _como_dict(row: Any) -> dict[str, Any]:
    if not row:
        return {}
    if isinstance(row, dict):
        return row
    return dict(row)


def _limite_seguro(limite: int | None) -> int:
    return max(1, min(int(limite or 50), 500))


def _resumo_decisao(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _nd(item.get("id")),
        "ticker": _nd(item.get("ticker")),
        "data_decisao": _nd(item.get("data_decisao")),
        "decisao": _nd(item.get("decisao")),
        "motivo": _nd(item.get("motivo")),
        "confianca": _nd(item.get("confianca")),
        "risco": _nd(item.get("risco")),
        "score_final": _nd(item.get("score_final")),
        "contexto_versao": _nd(item.get("contexto_versao")),
        "versao_motor": _nd(item.get("versao_motor")),
        "payload_hash": _nd(item.get("payload_hash")),
        "hash_valido": item.get("hash_valido") if item.get("hash_valido") is not None else NAO_DISPONIVEL,
    }


def _extrair_gates(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = payload or {}
    gates = payload.get("gates_detalhes") or {}
    if not isinstance(gates, dict):
        return []
    itens = []
    for chave, gate in sorted(gates.items(), key=lambda par: str(par[0])):
        gate = gate if isinstance(gate, dict) else {}
        itens.append({
            "gate": _nd(gate.get("gate", chave)),
            "status": _nd(gate.get("status")),
            "aprovado": gate.get("aprovado") if gate.get("aprovado") is not None else NAO_DISPONIVEL,
            "eliminado": gate.get("eliminado") if gate.get("eliminado") is not None else NAO_DISPONIVEL,
            "motivos": gate.get("motivos") or gate.get("motivo") or [],
            "metricas": gate.get("metricas") or {},
            "fontes": gate.get("fontes") or [],
            "penalidades": gate.get("penalidades") or [],
        })
    return itens


def _extrair_bloqueios(payload: dict[str, Any] | None, decisao: dict[str, Any]) -> list[dict[str, Any]]:
    payload = payload or {}
    bloqueios = []
    motivo_bloqueio = payload.get("motivo_bloqueio") or decisao.get("motivo")
    decisao_txt = str(decisao.get("decisao") or payload.get("decisao") or "").upper()
    if "BLOQUE" in decisao_txt or payload.get("permitir_decisao") is False:
        bloqueios.append({
            "ticker": _nd(decisao.get("ticker") or payload.get("ticker")),
            "decisao": _nd(decisao.get("decisao") or payload.get("decisao")),
            "gate_parada": _nd(payload.get("gate_parada")),
            "motivo": _nd(motivo_bloqueio),
        })
    for campo in ["campos_ausentes", "campos_vencidos", "fontes_falharam"]:
        valores = payload.get(campo) or []
        if isinstance(valores, str):
            valores = [valores]
        for valor in valores:
            bloqueios.append({
                "ticker": _nd(decisao.get("ticker") or payload.get("ticker")),
                "tipo": campo,
                "motivo": _nd(valor),
            })
    return bloqueios


def _extrair_fontes(payload: dict[str, Any] | None, decisao: dict[str, Any]) -> dict[str, Any]:
    payload = payload or {}
    return {
        "ticker": _nd(decisao.get("ticker") or payload.get("ticker")),
        "fonte_patrimonial": _nd(payload.get("fonte_patrimonial")),
        "nivel_uso_dados": _nd(payload.get("nivel_uso_dados")),
        "score_confianca_dados": _nd(payload.get("score_confianca_dados")),
        "contexto_versao": _nd(decisao.get("contexto_versao") or payload.get("contexto_versao")),
        "versao_motor": _nd(decisao.get("versao_motor") or payload.get("versao_motor") or payload.get("versao_modelo")),
        "payload_hash": _nd(decisao.get("payload_hash") or payload.get("payload_hash")),
    }


def gerar_relatorio_decisoes_auditaveis(*, limite: int = 50, incluir_replay: bool = False) -> dict[str, Any]:
    """Gera relatório auditável a partir de decisões persistidas."""
    limite_ok = _limite_seguro(limite)
    indice = listar_decisoes_auditaveis(limite=limite_ok)
    decisoes_indice = indice.get("decisoes", [])
    decisoes = []
    bloqueios = []
    fontes = []
    replays = []
    gates = []

    for item in decisoes_indice:
        decisao_id = item.get("id")
        detalhe = consultar_decisao_auditavel(int(decisao_id), incluir_payload=True, replay=incluir_replay) if decisao_id else {}
        decisao = detalhe.get("decisao") or item
        payload = detalhe.get("payload") or {}
        auditoria = detalhe.get("auditoria") or {}
        replay = detalhe.get("replay") or {"executado": False, "solicitado": bool(incluir_replay)}
        resumo = _resumo_decisao({**item, **decisao})
        resumo.update({
            "payload_hash_salvo": _nd(auditoria.get("payload_hash_salvo") or item.get("payload_hash")),
            "payload_hash_calculado": _nd(auditoria.get("payload_hash_calculado") or item.get("payload_hash_calculado")),
            "hash_valido": auditoria.get("hash_valido") if auditoria.get("hash_valido") is not None else item.get("hash_valido", NAO_DISPONIVEL),
        })
        decisoes.append(resumo)
        bloqueios.extend(_extrair_bloqueios(payload, decisao))
        fontes.append(_extrair_fontes(payload, decisao))
        for gate in _extrair_gates(payload):
            gates.append({"ticker": resumo["ticker"], **gate})
        replays.append({
            "decisao_id": _nd(decisao_id),
            "ticker": resumo["ticker"],
            "solicitado": bool(incluir_replay),
            "executado": replay.get("executado", False),
            "status": _nd(replay.get("status")),
            "replay_deterministico": replay.get("replay_deterministico") if replay.get("replay_deterministico") is not None else NAO_DISPONIVEL,
            "divergencia_replay": replay.get("divergencia_replay") if replay.get("divergencia_replay") is not None else NAO_DISPONIVEL,
            "payload_hash_salvo": _nd(replay.get("payload_hash_salvo") or resumo.get("payload_hash_salvo")),
            "payload_hash_replay": _nd(replay.get("payload_hash_replay")),
            "fonte_replay": _nd(replay.get("fonte_replay")),
        })

    return {
        "status": "ok",
        "tipo": "relatorio_auditavel",
        "versao_relatorio": VERSAO_RELATORIO,
        "gerado_em": _agora_iso(),
        "limite": limite_ok,
        "incluir_replay": bool(incluir_replay),
        "sem_scraping": True,
        "executou_motor": False,
        "alterou_decisao": False,
        "resumo": {
            "quantidade_decisoes": len(decisoes),
            "quantidade_bloqueios": len(bloqueios),
            "quantidade_fontes": len(fontes),
            "quantidade_gates": len(gates),
            "quantidade_replays": len(replays),
        },
        "decisoes": decisoes,
        "bloqueios": bloqueios,
        "fontes": fontes,
        "gates": gates,
        "replays": replays,
    }


def gerar_relatorio_carteira_auditavel() -> dict[str, Any]:
    """Gera relatório técnico de carteira por leitura local, sem motor/scraping."""
    try:
        rows = db.buscar_todos("SELECT * FROM carteira_posicoes ORDER BY ticker")
    except Exception:
        rows = []
    posicoes = []
    for row in rows:
        item = _como_dict(row)
        posicoes.append({
            "ticker": _nd(item.get("ticker")),
            "quantidade": _nd(item.get("quantidade")),
            "preco_medio": _nd(item.get("preco_medio")),
            "custo_total": _nd(item.get("custo_total")),
            "segmento": _nd(item.get("segmento")),
            "atualizado_em": _nd(item.get("atualizado_em")),
        })
    return {
        "status": "ok",
        "tipo": "relatorio_carteira_auditavel",
        "versao_relatorio": VERSAO_RELATORIO,
        "gerado_em": _agora_iso(),
        "sem_scraping": True,
        "executou_motor": False,
        "alterou_decisao": False,
        "resumo": {"quantidade_posicoes": len(posicoes)},
        "posicoes": posicoes,
    }


def gerar_relatorio_auditavel_completo(*, limite: int = 50, incluir_replay: bool = False) -> dict[str, Any]:
    decisoes = gerar_relatorio_decisoes_auditaveis(limite=limite, incluir_replay=incluir_replay)
    carteira = gerar_relatorio_carteira_auditavel()
    return {
        "status": "ok",
        "tipo": "relatorio_auditavel_completo",
        "versao_relatorio": VERSAO_RELATORIO,
        "gerado_em": _agora_iso(),
        "sem_scraping": True,
        "executou_motor": False,
        "alterou_decisao": False,
        "carteira": carteira,
        "decisoes": decisoes,
    }


def gerar_markdown_relatorio_auditavel(relatorio: dict[str, Any]) -> str:
    """Exporta relatório auditável em Markdown."""
    linhas = []
    linhas.append("# FIIA — Relatório Auditável")
    linhas.append("")
    linhas.append(f"- Gerado em: {_nd(relatorio.get('gerado_em'))}")
    linhas.append(f"- Versão do relatório: {_nd(relatorio.get('versao_relatorio'))}")
    linhas.append(f"- Sem scraping: {_nd(relatorio.get('sem_scraping'))}")
    linhas.append(f"- Executou motor: {_nd(relatorio.get('executou_motor'))}")
    linhas.append(f"- Alterou decisão: {_nd(relatorio.get('alterou_decisao'))}")
    linhas.append("")

    bloco_decisoes = relatorio.get("decisoes", {})
    if bloco_decisoes.get("tipo") == "relatorio_auditavel":
        decisoes = bloco_decisoes.get("decisoes", [])
    else:
        decisoes = bloco_decisoes.get("decisoes", {}).get("decisoes", []) if isinstance(bloco_decisoes.get("decisoes"), dict) else []
    if not decisoes and isinstance(bloco_decisoes, dict):
        decisoes = bloco_decisoes.get("decisoes", [])

    linhas.append("## Decisões")
    linhas.append("")
    if not decisoes:
        linhas.append("Nenhuma decisão disponível.")
    else:
        linhas.append("| ID | Ticker | Data | Decisão | Contexto | Motor | Hash | Hash válido |")
        linhas.append("|---:|---|---|---|---|---|---|---|")
        for item in decisoes:
            linhas.append(
                f"| {_nd(item.get('id'))} | {_nd(item.get('ticker'))} | {_nd(item.get('data_decisao'))} | "
                f"{_nd(item.get('decisao'))} | {_nd(item.get('contexto_versao'))} | {_nd(item.get('versao_motor'))} | "
                f"{_nd(item.get('payload_hash'))} | {_nd(item.get('hash_valido'))} |"
            )
    linhas.append("")

    bloqueios = bloco_decisoes.get("bloqueios", []) if isinstance(bloco_decisoes, dict) else []
    linhas.append("## Bloqueios e falhas")
    linhas.append("")
    if not bloqueios:
        linhas.append("Nenhum bloqueio disponível.")
    else:
        for item in bloqueios:
            linhas.append(f"- {_nd(item.get('ticker'))}: {_nd(item.get('tipo', item.get('decisao')))} — {_nd(item.get('motivo'))}")
    linhas.append("")

    replays = bloco_decisoes.get("replays", []) if isinstance(bloco_decisoes, dict) else []
    linhas.append("## Replay")
    linhas.append("")
    if not replays:
        linhas.append("Replay não disponível.")
    else:
        for item in replays:
            linhas.append(
                f"- Decisão {_nd(item.get('decisao_id'))} / {_nd(item.get('ticker'))}: "
                f"executado={_nd(item.get('executado'))}, status={_nd(item.get('status'))}, "
                f"divergência={_nd(item.get('divergencia_replay'))}"
            )
    linhas.append("")
    return "\n".join(linhas)
