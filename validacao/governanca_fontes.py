"""
validacao/governanca_fontes.py

Camada de governança de fontes do FIIA.

Objetivo:
- medir disponibilidade, frescor, divergência e confiabilidade histórica;
- classificar cada fonte como OK, VENCIDA, DIVERGENTE, INDISPONIVEL ou SUSPEITA;
- não alterar decisão, gates, thresholds ou motor;
- permitir testes unitários sem rede.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from statistics import mean
from typing import Any

from banco import db
from sistema import observabilidade

STATUS_OK = "OK"
STATUS_VENCIDA = "VENCIDA"
STATUS_DIVERGENTE = "DIVERGENTE"
STATUS_INDISPONIVEL = "INDISPONIVEL"
STATUS_SUSPEITA = "SUSPEITA"
STATUS_VALIDOS = {STATUS_OK, STATUS_VENCIDA, STATUS_DIVERGENTE, STATUS_INDISPONIVEL, STATUS_SUSPEITA}

FONTES_MONITORADAS = ("CVM", "FNET", "YAHOO", "FUNDAMENTUS", "BCB")

FRESCOR_PADRAO_DIAS = {
    "CVM": 95,
    "FNET": 45,
    "YAHOO": 3,
    "FUNDAMENTUS": 7,
    "BCB": 5,
}


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_data(valor: Any) -> date | None:
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor)
    for tamanho, formato in ((10, "%Y-%m-%d"), (7, "%Y-%m")):
        try:
            return datetime.strptime(texto[:tamanho], formato).date()
        except Exception:
            continue
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).date()
    except Exception:
        return None


def _idade_dias(data_ultima: Any, data_referencia: date | None = None) -> int | None:
    data = _parse_data(data_ultima)
    if not data:
        return None
    ref = data_referencia or date.today()
    return (ref - data).days


def _score_confianca(status: str, idade: int | None, divergencia_pct: float | None, disponibilidade_pct: float | None) -> float:
    base = {
        STATUS_OK: 100.0,
        STATUS_VENCIDA: 55.0,
        STATUS_DIVERGENTE: 45.0,
        STATUS_INDISPONIVEL: 0.0,
        STATUS_SUSPEITA: 35.0,
    }.get(status, 0.0)
    if idade is not None and idade > 0:
        base -= min(20.0, idade / 10.0)
    if divergencia_pct is not None:
        base -= min(30.0, abs(divergencia_pct) * 100)
    if disponibilidade_pct is not None:
        base = (base * 0.7) + (max(0.0, min(100.0, disponibilidade_pct)) * 0.3)
    return round(max(0.0, min(100.0, base)), 2)


def classificar_fonte(
    *,
    fonte: str,
    disponivel: bool,
    data_ultima: Any = None,
    valor_principal: float | None = None,
    valor_referencia: float | None = None,
    max_idade_dias: int | None = None,
    tolerancia_divergencia_pct: float = 0.02,
    disponibilidade_pct: float | None = None,
    data_referencia: date | None = None,
) -> dict[str, Any]:
    """Classifica uma fonte sem chamar rede nem alterar dados de decisão."""
    fonte_norm = fonte.upper().strip()
    max_idade = max_idade_dias if max_idade_dias is not None else FRESCOR_PADRAO_DIAS.get(fonte_norm, 30)
    idade = _idade_dias(data_ultima, data_referencia=data_referencia)
    divergencia_pct = None

    if not disponivel:
        status = STATUS_INDISPONIVEL
        motivo = "Fonte indisponível ou sem payload utilizável."
    elif idade is None:
        status = STATUS_SUSPEITA
        motivo = "Fonte disponível, mas sem data de atualização confiável."
    elif idade > max_idade:
        status = STATUS_VENCIDA
        motivo = f"Fonte vencida: idade {idade} dias acima do limite {max_idade}."
    else:
        status = STATUS_OK
        motivo = "Fonte disponível e dentro do frescor esperado."

    if disponivel and valor_principal is not None and valor_referencia not in (None, 0):
        divergencia_pct = abs(float(valor_principal) - float(valor_referencia)) / abs(float(valor_referencia))
        if divergencia_pct > tolerancia_divergencia_pct:
            status = STATUS_DIVERGENTE
            motivo = f"Fonte divergente: diferença {round(divergencia_pct * 100, 2)}% acima da tolerância {round(tolerancia_divergencia_pct * 100, 2)}%."

    score = _score_confianca(status, idade, divergencia_pct, disponibilidade_pct)
    return {
        "fonte": fonte_norm,
        "status": status,
        "motivo": motivo,
        "idade_dias": idade,
        "max_idade_dias": max_idade,
        "divergencia_pct": round(divergencia_pct * 100, 4) if divergencia_pct is not None else None,
        "disponibilidade_pct": disponibilidade_pct,
        "score_confianca_fonte": score,
    }


def garantir_tabela_governanca_fontes() -> None:
    db.executar(
        """
        CREATE TABLE IF NOT EXISTS governanca_fontes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fonte TEXT NOT NULL,
            ticker TEXT,
            data_referencia TEXT NOT NULL,
            status TEXT NOT NULL,
            motivo TEXT,
            idade_dias INTEGER,
            max_idade_dias INTEGER,
            divergencia_pct REAL,
            disponibilidade_pct REAL,
            score_confianca_fonte REAL,
            payload_json TEXT,
            criado_em TEXT NOT NULL,
            CHECK(status IN ('OK', 'VENCIDA', 'DIVERGENTE', 'INDISPONIVEL', 'SUSPEITA'))
        )
        """
    )
    db.executar("CREATE INDEX IF NOT EXISTS idx_governanca_fontes_fonte_data ON governanca_fontes(fonte, data_referencia)")
    db.executar("CREATE INDEX IF NOT EXISTS idx_governanca_fontes_ticker ON governanca_fontes(ticker)")


def registrar_status_fonte(
    status_fonte: dict[str, Any],
    *,
    ticker: str | None = None,
    data_referencia: str | date | None = None,
    persistir: bool = True,
) -> dict[str, Any]:
    """Registra status de fonte em tabela aditiva e log estruturado."""
    fonte = str(status_fonte.get("fonte") or "").upper()
    status = str(status_fonte.get("status") or STATUS_SUSPEITA).upper()
    if status not in STATUS_VALIDOS:
        status = STATUS_SUSPEITA
    data_ref = data_referencia.isoformat() if isinstance(data_referencia, date) else (data_referencia or date.today().isoformat())
    payload = {
        **status_fonte,
        "fonte": fonte,
        "status": status,
        "ticker": ticker.upper().replace(".SA", "") if ticker else None,
        "data_referencia": data_ref,
    }

    observabilidade.registrar_evento(
        "INFO" if status == STATUS_OK else "WARN",
        "validacao.governanca_fontes",
        "Status de fonte registrado",
        ticker=payload.get("ticker"),
        fonte=fonte,
        contexto={
            "status": status,
            "idade_dias": payload.get("idade_dias"),
            "divergencia_pct": payload.get("divergencia_pct"),
            "score_confianca_fonte": payload.get("score_confianca_fonte"),
        },
    )

    if persistir:
        garantir_tabela_governanca_fontes()
        db.executar(
            """
            INSERT INTO governanca_fontes
            (fonte, ticker, data_referencia, status, motivo, idade_dias, max_idade_dias,
             divergencia_pct, disponibilidade_pct, score_confianca_fonte, payload_json, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fonte,
                payload.get("ticker"),
                data_ref,
                status,
                payload.get("motivo"),
                payload.get("idade_dias"),
                payload.get("max_idade_dias"),
                payload.get("divergencia_pct"),
                payload.get("disponibilidade_pct"),
                payload.get("score_confianca_fonte"),
                json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
                _agora_iso(),
            ),
        )
    return payload


def consolidar_status_fontes(statuses: list[dict[str, Any]]) -> dict[str, Any]:
    """Consolida múltiplas fontes sem alterar decisão final."""
    if not statuses:
        return {
            "status_global": STATUS_INDISPONIVEL,
            "score_confianca_global": 0.0,
            "fontes": [],
            "motivos": ["Nenhuma fonte monitorada."],
        }
    scores = [float(s.get("score_confianca_fonte") or 0.0) for s in statuses]
    status_por_fonte = {s.get("fonte"): s.get("status") for s in statuses}
    if any(s.get("status") == STATUS_DIVERGENTE for s in statuses):
        status_global = STATUS_DIVERGENTE
    elif any(s.get("status") == STATUS_INDISPONIVEL for s in statuses):
        status_global = STATUS_SUSPEITA
    elif any(s.get("status") == STATUS_VENCIDA for s in statuses):
        status_global = STATUS_VENCIDA
    elif all(s.get("status") == STATUS_OK for s in statuses):
        status_global = STATUS_OK
    else:
        status_global = STATUS_SUSPEITA
    return {
        "status_global": status_global,
        "score_confianca_global": round(mean(scores), 2),
        "status_por_fonte": status_por_fonte,
        "fontes": statuses,
        "motivos": [s.get("motivo") for s in statuses if s.get("motivo")],
    }


def avaliar_fontes_por_payloads(
    payloads: dict[str, dict[str, Any]],
    *,
    ticker: str | None = None,
    data_referencia: str | date | None = None,
    persistir: bool = False,
) -> dict[str, Any]:
    """
    Avalia fontes a partir de payloads já fornecidos.

    Não aciona rede. Espera payloads com chaves como:
    disponivel, data_ultima, valor_principal, valor_referencia,
    max_idade_dias, tolerancia_divergencia_pct e disponibilidade_pct.
    """
    resultados = []
    for fonte in FONTES_MONITORADAS:
        payload = payloads.get(fonte) or payloads.get(fonte.lower()) or {}
        status = classificar_fonte(
            fonte=fonte,
            disponivel=bool(payload.get("disponivel")),
            data_ultima=payload.get("data_ultima"),
            valor_principal=payload.get("valor_principal"),
            valor_referencia=payload.get("valor_referencia"),
            max_idade_dias=payload.get("max_idade_dias"),
            tolerancia_divergencia_pct=float(payload.get("tolerancia_divergencia_pct", 0.02)),
            disponibilidade_pct=payload.get("disponibilidade_pct"),
            data_referencia=_parse_data(data_referencia) if data_referencia else None,
        )
        resultados.append(registrar_status_fonte(status, ticker=ticker, data_referencia=data_referencia, persistir=persistir))
    return consolidar_status_fontes(resultados)
