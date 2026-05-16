"""
aprendizado/calibracao_ia.py
Mede se o score qualitativo da IA agrega sinal real às decisões do FIIA.

Regra de governança:
- não usa IA como critério eliminatório;
- não altera pesos automaticamente;
- apenas mede correlação e sinaliza quando há amostra suficiente.
"""
from __future__ import annotations

from math import sqrt
from typing import Any

from banco import db
from config.settings import APRENDIZADO_AMOSTRAS_MINIMAS
from sistema import observabilidade


def _row_get(row: Any, chave: str, padrao: Any = None) -> Any:
    try:
        return row[chave]
    except Exception:
        return padrao


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den_x = sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = sqrt(sum((y - my) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def _rank(vals: list[float]) -> list[float]:
    pares = sorted((v, i) for i, v in enumerate(vals))
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(pares):
        j = i
        while j + 1 < len(pares) and pares[j + 1][0] == pares[i][0]:
            j += 1
        rank_medio = (i + j + 2) / 2
        for k in range(i, j + 1):
            ranks[pares[k][1]] = rank_medio
        i = j + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    return _pearson(_rank(xs), _rank(ys))


def analisar_calibracao_ia(janela_dias: int = 365, min_amostras: int | None = None) -> dict[str, Any]:
    """Mede correlação score_ia x resultado real por segmento."""
    min_amostras = min_amostras or APRENDIZADO_AMOSTRAS_MINIMAS
    rows = db.buscar_todos(
        """
        SELECT d.ticker, d.score_ia, r.acerto, r.retorno_total, r.retorno_cdi_periodo,
               COALESCE(f.segmento, 'INDEFINIDO') AS segmento
        FROM decisoes d
        JOIN decisoes_resultado r ON r.decisao_id = d.id
        LEFT JOIN fiis f ON f.ticker = d.ticker
        WHERE d.score_ia IS NOT NULL
          AND r.janela_dias = ?
        """,
        (janela_dias,),
    )

    grupos: dict[str, list[dict[str, Any]]] = {"GERAL": []}
    for row in rows:
        score = _row_get(row, "score_ia")
        if score is None:
            continue
        item = dict(row)
        item["excesso_cdi"] = float(item.get("retorno_total") or 0) - float(item.get("retorno_cdi_periodo") or 0)
        grupos["GERAL"].append(item)
        seg = item.get("segmento") or "INDEFINIDO"
        grupos.setdefault(seg, []).append(item)

    resultado: dict[str, Any] = {
        "janela_dias": janela_dias,
        "min_amostras": min_amostras,
        "usa_ia_como_eliminatorio": False,
        "altera_pesos_automaticamente": False,
        "segmentos": {},
    }

    for segmento, itens in grupos.items():
        total = len(itens)
        scores = [float(i["score_ia"]) for i in itens]
        acertos = [float(i["acerto"] or 0) for i in itens]
        excessos = [float(i["excesso_cdi"] or 0) for i in itens]
        corr_acerto = _spearman(scores, acertos) if total >= 2 else None
        corr_excesso = _spearman(scores, excessos) if total >= 2 else None
        amostra_suficiente = total >= min_amostras

        if corr_excesso is None:
            leitura = "SEM_SINAL_MEDIVEL"
        elif corr_excesso >= 0.25:
            leitura = "IA_AGREGA_SINAL"
        elif corr_excesso <= -0.25:
            leitura = "IA_ADICIONA_RUIDO"
        else:
            leitura = "SINAL_FRACO_OU_NEUTRO"

        resultado["segmentos"][segmento] = {
            "total": total,
            "amostra_suficiente": amostra_suficiente,
            "correlacao_score_acerto": round(corr_acerto, 4) if corr_acerto is not None else None,
            "correlacao_score_excesso_cdi": round(corr_excesso, 4) if corr_excesso is not None else None,
            "leitura": leitura,
            "acao_recomendada": (
                "Apenas observar; amostra insuficiente para calibrar."
                if not amostra_suficiente
                else "Pode ser usado para revisão humana de pesos, sem aplicação automática."
            ),
        }

    observabilidade.registrar_evento(
        "INFO",
        "aprendizado.calibracao_ia",
        "Calibração do score IA calculada",
        contexto={"janela_dias": janela_dias, "segmentos": list(resultado["segmentos"].keys())},
    )
    return resultado


def resumo_calibracao_ia() -> dict[str, Any]:
    """Resumo nas janelas principais usadas pelo avaliador."""
    return {
        "90d": analisar_calibracao_ia(90),
        "365d": analisar_calibracao_ia(365),
    }
