"""
aprendizado/pesos_fnet.py

Governança de pesos documentais FNET.

Objetivo:
- analisar simulações marcadas como fnet_score_v1;
- medir falsos positivos/falsos negativos por risco documental;
- sugerir ajuste gradual de peso sem aplicar automaticamente;
- preservar rastreabilidade por evidência.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from banco import db
from aprendizado.tentativa_erro import garantir_tabelas, sugerir_ajuste_peso
from sistema import observabilidade

PESO_BASE = {
    "SEM_FNET": -5.0,
    "BAIXO": 0.0,
    "MEDIO": -10.0,
    "ALTO": -30.0,
    "ERRO": -100.0,
}


def _json(valor: Any) -> dict[str, Any]:
    if not valor:
        return {}
    if isinstance(valor, dict):
        return valor
    try:
        return json.loads(valor)
    except Exception:
        return {}


def _limitar(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def _calcular_sugestao(nivel: str, peso_atual: float, taxa_fp: float, taxa_fn: float) -> float:
    """
    Ajuste conservador:
    - falso positivo alto aumenta penalização;
    - falso negativo alto reduz penalização;
    - mudança máxima por ciclo: 5 pontos.
    """
    ajuste = 0.0

    if taxa_fp >= 0.35:
        ajuste -= 5.0
    elif taxa_fp >= 0.25:
        ajuste -= 2.5

    if taxa_fn >= 0.35:
        ajuste += 5.0
    elif taxa_fn >= 0.25:
        ajuste += 2.5

    novo = peso_atual + ajuste

    limites = {
        "SEM_FNET": (-20.0, 0.0),
        "BAIXO": (-5.0, 5.0),
        "MEDIO": (-30.0, 0.0),
        "ALTO": (-60.0, -10.0),
        "ERRO": (-100.0, -20.0),
    }
    minimo, maximo = limites.get(nivel, (-60.0, 5.0))
    return round(_limitar(novo, minimo, maximo), 2)


def analisar_pesos_fnet(min_amostras: int = 5) -> dict[str, Any]:
    """Analisa desempenho histórico das decisões com peso FNET."""
    garantir_tabelas()

    rows = db.buscar_todos(
        """
        SELECT
            s.id AS simulacao_id,
            s.ticker,
            s.payload_json,
            s.score_final,
            s.peso_versao,
            r.resultado,
            r.falso_positivo,
            r.falso_negativo,
            r.janela_dias,
            r.retorno_pct
        FROM aprendizado_simulacoes s
        JOIN aprendizado_resultados r ON r.simulacao_id = s.id
        WHERE s.peso_versao = 'fnet_score_v1'
        """
    )

    grupos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        payload = _json(row["payload_json"])
        nivel = payload.get("risco_documental_fnet") or "INDEFINIDO"
        grupos[nivel].append({**dict(row), "payload": payload})

    resumo_niveis = []
    sugestoes = []

    for nivel, itens in grupos.items():
        total = len(itens)
        fp = sum(int(i.get("falso_positivo") or 0) for i in itens)
        fn = sum(int(i.get("falso_negativo") or 0) for i in itens)
        acertos = sum(1 for i in itens if i.get("resultado") == "ACERTO")
        taxa_fp = fp / total if total else 0
        taxa_fn = fn / total if total else 0
        taxa_acerto = acertos / total if total else 0
        peso_atual = PESO_BASE.get(nivel, 0.0)
        peso_sugerido = _calcular_sugestao(nivel, peso_atual, taxa_fp, taxa_fn)

        item_resumo = {
            "nivel_risco_documental": nivel,
            "amostras": total,
            "acertos": acertos,
            "acerto_pct": round(taxa_acerto, 4),
            "falso_positivo_pct": round(taxa_fp, 4),
            "falso_negativo_pct": round(taxa_fn, 4),
            "peso_atual": peso_atual,
            "peso_sugerido": peso_sugerido,
            "suficiente": total >= min_amostras,
        }
        resumo_niveis.append(item_resumo)

        if total >= min_amostras and peso_sugerido != peso_atual:
            evidencia = json.dumps(item_resumo, ensure_ascii=False)
            ajuste = sugerir_ajuste_peso(
                regra=f"FNET:{nivel}",
                peso_anterior=peso_atual,
                peso_sugerido=peso_sugerido,
                motivo="Ajuste sugerido por desempenho histórico de simulações FNET.",
                evidencia=evidencia,
            )
            sugestoes.append(ajuste)

    resultado = {
        "status": "ok",
        "min_amostras": min_amostras,
        "total_resultados_fnet": len(rows),
        "resumo_por_nivel": resumo_niveis,
        "sugestoes_criadas": sugestoes,
    }

    observabilidade.registrar_evento(
        "INFO",
        "aprendizado.pesos_fnet",
        "Pesos FNET analisados",
        contexto={"total_resultados_fnet": len(rows), "sugestoes": len(sugestoes)},
    )
    return resultado
