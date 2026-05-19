"""
operacional/healthcheck.py

Healthchecks e jobs operacionais do FIIA.

Contratos:
- health básico não aciona scraping;
- health profundo é explícito;
- jobs registram status estruturado;
- falhas retornam motivo operacional sem stacktrace;
- não altera motor, decisão ou contrato final.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from banco import db
from config import settings
from sistema import observabilidade

STATUS_OK = "OK"
STATUS_ALERTA = "ALERTA"
STATUS_ERRO = "ERRO"
STATUS_NAO_EXECUTADO = "NAO_EXECUTADO"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_global(itens: list[dict[str, Any]]) -> str:
    if any(item.get("status") == STATUS_ERRO for item in itens):
        return STATUS_ERRO
    if any(item.get("status") in {STATUS_ALERTA, STATUS_NAO_EXECUTADO} for item in itens):
        return STATUS_ALERTA
    return STATUS_OK


def _resposta(nome: str, componentes: list[dict[str, Any]], *, profundo: bool = False) -> dict[str, Any]:
    status = _status_global(componentes)
    return {
        "status": status,
        "nome": nome,
        "profundo": bool(profundo),
        "timestamp": _agora_iso(),
        "componentes": componentes,
        "sem_scraping": True,
        "executou_motor": False,
        "alterou_decisao": False,
    }


def verificar_api_basica() -> dict[str, Any]:
    return {
        "componente": "api",
        "status": STATUS_OK,
        "motivo": "Processo respondeu ao healthcheck básico.",
    }


def verificar_configuracao() -> dict[str, Any]:
    resultado = settings.validar_configuracao_seguranca()
    if resultado.get("seguro"):
        return {
            "componente": "configuracao",
            "status": STATUS_OK,
            "motivo": "Configuração compatível com o ambiente atual.",
            "ambiente": resultado.get("ambiente"),
            "producao": resultado.get("producao"),
            "debug": resultado.get("debug"),
        }
    return {
        "componente": "configuracao",
        "status": STATUS_ERRO,
        "motivo": "Configuração de segurança inválida para o ambiente atual.",
        "ambiente": resultado.get("ambiente"),
        "producao": resultado.get("producao"),
        "debug": resultado.get("debug"),
        "problemas": resultado.get("problemas", []),
    }


def verificar_observabilidade() -> dict[str, Any]:
    ativa = observabilidade.observabilidade_ativa()
    return {
        "componente": "observabilidade",
        "status": STATUS_OK if ativa else STATUS_ALERTA,
        "motivo": "Observabilidade ativa." if ativa else "Observabilidade desativada por configuração.",
        "ativa": ativa,
    }


def verificar_banco_basico() -> dict[str, Any]:
    """Verifica banco com SELECT 1. Não inicializa, não migra e não faz scraping."""
    try:
        row = db.buscar_um("SELECT 1 AS ok")
        ok = bool(row and row["ok"] == 1)
        return {
            "componente": "banco",
            "status": STATUS_OK if ok else STATUS_ERRO,
            "motivo": "Banco respondeu SELECT 1." if ok else "Banco não retornou resposta esperada.",
        }
    except Exception as erro:
        return {
            "componente": "banco",
            "status": STATUS_ERRO,
            "motivo": "Banco indisponível ou inacessível.",
            "tipo_erro": type(erro).__name__,
        }


def verificar_tabelas_minimas() -> dict[str, Any]:
    """Verifica presença de tabelas críticas sem criar schema."""
    tabelas = ["decisoes", "indicadores", "carteira", "macro"]
    try:
        rows = db.buscar_todos(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?, ?, ?, ?)",
            tuple(tabelas),
        )
        existentes = sorted([row["name"] for row in rows])
        faltantes = sorted(set(tabelas) - set(existentes))
        return {
            "componente": "banco_tabelas",
            "status": STATUS_OK if not faltantes else STATUS_ALERTA,
            "motivo": "Tabelas mínimas presentes." if not faltantes else "Há tabelas mínimas ausentes; execute setup/migração.",
            "existentes": existentes,
            "faltantes": faltantes,
        }
    except Exception as erro:
        return {
            "componente": "banco_tabelas",
            "status": STATUS_ERRO,
            "motivo": "Falha controlada ao verificar tabelas mínimas.",
            "tipo_erro": type(erro).__name__,
        }


def verificar_fontes_criticas_sem_rede() -> dict[str, Any]:
    """
    Verifica cobertura local de fontes críticas sem rede.

    Não chama CVM, FNET, Yahoo, Fundamentus ou BCB. Apenas verifica sinais locais,
    quando tabelas existem.
    """
    fontes = {
        "CVM": "cvm_informes_mensais_fii",
        "FNET": "fnet_dividendos_fii",
        "BCB": "macro",
        "YAHOO": "indicadores",
        "FUNDAMENTUS": "indicadores",
    }
    resultados = []
    try:
        for fonte, tabela in fontes.items():
            try:
                row = db.buscar_um(f"SELECT COUNT(*) AS total FROM {tabela}")
                total = int(row["total"] if row else 0)
                resultados.append({
                    "fonte": fonte,
                    "status": STATUS_OK if total > 0 else STATUS_ALERTA,
                    "motivo": "Há registros locais." if total > 0 else "Sem registros locais encontrados; não foi feita consulta externa.",
                    "registros_locais": total,
                })
            except Exception as erro_fonte:
                resultados.append({
                    "fonte": fonte,
                    "status": STATUS_ALERTA,
                    "motivo": "Tabela local ausente ou inacessível; não foi feita consulta externa.",
                    "tipo_erro": type(erro_fonte).__name__,
                    "registros_locais": None,
                })
        return {
            "componente": "fontes_criticas",
            "status": _status_global(resultados),
            "motivo": "Fontes críticas verificadas por sinais locais, sem rede.",
            "fontes": resultados,
        }
    except Exception as erro:
        return {
            "componente": "fontes_criticas",
            "status": STATUS_ERRO,
            "motivo": "Falha controlada ao verificar fontes críticas sem rede.",
            "tipo_erro": type(erro).__name__,
        }


def verificar_radar_operacional(*, executar: bool = False, executor: Callable[[], Any] | None = None) -> dict[str, Any]:
    """
    Verifica status operacional do Radar.

    Por padrão NÃO executa o Radar para evitar scraping/coleta. A execução real só
    ocorre se `executar=True` e um `executor` explícito for fornecido por camada
    autorizada futura.
    """
    if not executar:
        return {
            "componente": "radar",
            "status": STATUS_NAO_EXECUTADO,
            "motivo": "Radar não executado no healthcheck. Execução exige chamada explícita.",
            "execucao_explicita_requerida": True,
        }
    if executor is None:
        return {
            "componente": "radar",
            "status": STATUS_ALERTA,
            "motivo": "Execução explícita solicitada, mas nenhum executor autorizado foi fornecido.",
            "execucao_explicita_requerida": True,
        }
    try:
        resultado = executor()
        quantidade = len(resultado) if isinstance(resultado, list) else None
        return {
            "componente": "radar",
            "status": STATUS_OK,
            "motivo": "Radar executado por executor explícito autorizado.",
            "quantidade_oportunidades": quantidade,
        }
    except Exception as erro:
        return {
            "componente": "radar",
            "status": STATUS_ERRO,
            "motivo": "Falha controlada ao executar Radar explicitamente.",
            "tipo_erro": type(erro).__name__,
        }


def healthcheck_basico() -> dict[str, Any]:
    componentes = [verificar_api_basica(), verificar_configuracao(), verificar_observabilidade()]
    resposta = _resposta("healthcheck_basico", componentes, profundo=False)
    observabilidade.registrar_evento(
        "INFO" if resposta["status"] == STATUS_OK else "WARN",
        "operacional.healthcheck",
        "Healthcheck básico executado",
        contexto={"status": resposta["status"], "profundo": False},
    )
    return resposta


def healthcheck_profundo(*, incluir_radar: bool = False) -> dict[str, Any]:
    componentes = [
        verificar_api_basica(),
        verificar_configuracao(),
        verificar_observabilidade(),
        verificar_banco_basico(),
        verificar_tabelas_minimas(),
        verificar_fontes_criticas_sem_rede(),
        verificar_radar_operacional(executar=incluir_radar),
    ]
    resposta = _resposta("healthcheck_profundo", componentes, profundo=True)
    resposta["radar_explicito_solicitado"] = bool(incluir_radar)
    observabilidade.registrar_evento(
        "INFO" if resposta["status"] == STATUS_OK else "WARN",
        "operacional.healthcheck",
        "Healthcheck profundo executado",
        contexto={
            "status": resposta["status"],
            "profundo": True,
            "radar_explicito_solicitado": bool(incluir_radar),
        },
    )
    return resposta


def registrar_status_job(nome: str, status: str, motivo: str, *, contexto: dict[str, Any] | None = None) -> dict[str, Any]:
    status_norm = status.upper().strip() if status else STATUS_ALERTA
    if status_norm not in {STATUS_OK, STATUS_ALERTA, STATUS_ERRO, STATUS_NAO_EXECUTADO}:
        status_norm = STATUS_ALERTA
    evento = {
        "job": nome,
        "status": status_norm,
        "motivo": motivo,
        "timestamp": _agora_iso(),
        "contexto": contexto or {},
    }
    observabilidade.registrar_evento(
        "INFO" if status_norm == STATUS_OK else "WARN",
        "operacional.jobs",
        "Status de job operacional registrado",
        contexto=evento,
    )
    return evento


def job_verificacao_operacional() -> dict[str, Any]:
    """Job seguro de verificação operacional sem scraping."""
    resultado = healthcheck_profundo(incluir_radar=False)
    return registrar_status_job(
        "verificacao_operacional",
        resultado["status"],
        "Verificação operacional executada sem scraping e sem motor.",
        contexto={"componentes": resultado.get("componentes", [])},
    )
