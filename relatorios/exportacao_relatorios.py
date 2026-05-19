"""
relatorios/exportacao_relatorios.py

Exportação CSV/JSON de relatórios auditáveis do FIIA.

Contratos:
- não altera dados;
- não aciona scraping;
- não chama motor;
- campos exportados são estáveis;
- dados sensíveis não são exportados.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from relatorios.relatorios_auditaveis import gerar_relatorio_auditavel_completo, NAO_DISPONIVEL

CAMPOS_DECISOES = [
    "id",
    "ticker",
    "data_decisao",
    "decisao",
    "motivo",
    "confianca",
    "risco",
    "score_final",
    "contexto_versao",
    "versao_motor",
    "payload_hash",
    "hash_valido",
]

CAMPOS_FONTES = [
    "ticker",
    "fonte_patrimonial",
    "nivel_uso_dados",
    "score_confianca_dados",
    "contexto_versao",
    "versao_motor",
    "payload_hash",
]

CAMPOS_BLOQUEIOS = [
    "ticker",
    "tipo",
    "decisao",
    "gate_parada",
    "motivo",
]

CAMPOS_REPLAY = [
    "decisao_id",
    "ticker",
    "solicitado",
    "executado",
    "status",
    "replay_deterministico",
    "divergencia_replay",
    "payload_hash_salvo",
    "payload_hash_replay",
    "fonte_replay",
]

CAMPOS_METRICAS = [
    "quantidade_decisoes",
    "quantidade_bloqueios",
    "quantidade_fontes",
    "quantidade_gates",
    "quantidade_replays",
    "quantidade_posicoes",
    "sem_scraping",
    "executou_motor",
    "alterou_decisao",
]

SECOES_CAMPOS = {
    "decisoes": CAMPOS_DECISOES,
    "fontes": CAMPOS_FONTES,
    "bloqueios": CAMPOS_BLOQUEIOS,
    "replay": CAMPOS_REPLAY,
    "metricas": CAMPOS_METRICAS,
}

SECOES_VALIDAS = set(SECOES_CAMPOS)

CHAVES_SENSIVEIS = {
    "api_key",
    "apikey",
    "x-api-key",
    "gemini_api_key",
    "token",
    "secret",
    "senha",
    "password",
    "authorization",
    "cookie",
}


def _nd(valor: Any) -> Any:
    if valor is None or valor == "":
        return NAO_DISPONIVEL
    if isinstance(valor, (dict, list)):
        return json.dumps(_remover_sensiveis(valor), ensure_ascii=False, sort_keys=True, default=str)
    return valor


def _remover_sensiveis(valor: Any) -> Any:
    if isinstance(valor, dict):
        limpo = {}
        for chave, item in valor.items():
            chave_txt = str(chave).lower()
            if any(sensivel in chave_txt for sensivel in CHAVES_SENSIVEIS):
                continue
            limpo[chave] = _remover_sensiveis(item)
        return limpo
    if isinstance(valor, list):
        return [_remover_sensiveis(item) for item in valor]
    return valor


def _linha_estavel(item: dict[str, Any], campos: list[str]) -> dict[str, Any]:
    return {campo: _nd(item.get(campo)) for campo in campos}


def _linhas_secao(relatorio: dict[str, Any], secao: str) -> list[dict[str, Any]]:
    bloco_decisoes = relatorio.get("decisoes", {}) if isinstance(relatorio.get("decisoes"), dict) else {}
    if secao == "decisoes":
        return [_linha_estavel(item, CAMPOS_DECISOES) for item in bloco_decisoes.get("decisoes", [])]
    if secao == "fontes":
        return [_linha_estavel(item, CAMPOS_FONTES) for item in bloco_decisoes.get("fontes", [])]
    if secao == "bloqueios":
        return [_linha_estavel(item, CAMPOS_BLOQUEIOS) for item in bloco_decisoes.get("bloqueios", [])]
    if secao == "replay":
        return [_linha_estavel(item, CAMPOS_REPLAY) for item in bloco_decisoes.get("replays", [])]
    if secao == "metricas":
        resumo_decisoes = bloco_decisoes.get("resumo", {}) if isinstance(bloco_decisoes.get("resumo"), dict) else {}
        resumo_carteira = relatorio.get("carteira", {}).get("resumo", {}) if isinstance(relatorio.get("carteira"), dict) else {}
        item = {
            "quantidade_decisoes": resumo_decisoes.get("quantidade_decisoes"),
            "quantidade_bloqueios": resumo_decisoes.get("quantidade_bloqueios"),
            "quantidade_fontes": resumo_decisoes.get("quantidade_fontes"),
            "quantidade_gates": resumo_decisoes.get("quantidade_gates"),
            "quantidade_replays": resumo_decisoes.get("quantidade_replays"),
            "quantidade_posicoes": resumo_carteira.get("quantidade_posicoes"),
            "sem_scraping": relatorio.get("sem_scraping"),
            "executou_motor": relatorio.get("executou_motor"),
            "alterou_decisao": relatorio.get("alterou_decisao"),
        }
        return [_linha_estavel(item, CAMPOS_METRICAS)]
    return []


def gerar_exportacao_json(*, secao: str = "decisoes", limite: int = 50, incluir_replay: bool = False) -> dict[str, Any]:
    secao_norm = str(secao or "decisoes").lower().strip()
    if secao_norm not in SECOES_VALIDAS:
        return {
            "status": "erro",
            "mensagem": "Seção de exportação inválida.",
            "secoes_validas": sorted(SECOES_VALIDAS),
        }
    relatorio = gerar_relatorio_auditavel_completo(limite=limite, incluir_replay=incluir_replay)
    linhas = _linhas_secao(relatorio, secao_norm)
    return {
        "status": "ok",
        "formato": "json",
        "secao": secao_norm,
        "campos": SECOES_CAMPOS[secao_norm],
        "quantidade": len(linhas),
        "gerado_em": relatorio.get("gerado_em"),
        "versao_relatorio": relatorio.get("versao_relatorio"),
        "sem_scraping": True,
        "executou_motor": False,
        "alterou_decisao": False,
        "dados_sensiveis_exportados": False,
        "dados": linhas,
    }


def gerar_exportacao_csv(*, secao: str = "decisoes", limite: int = 50, incluir_replay: bool = False) -> dict[str, Any]:
    exportacao = gerar_exportacao_json(secao=secao, limite=limite, incluir_replay=incluir_replay)
    if exportacao.get("status") != "ok":
        return exportacao
    campos = exportacao["campos"]
    saida = io.StringIO()
    writer = csv.DictWriter(saida, fieldnames=campos, extrasaction="ignore")
    writer.writeheader()
    for item in exportacao["dados"]:
        writer.writerow({campo: _nd(item.get(campo)) for campo in campos})
    return {
        "status": "ok",
        "formato": "csv",
        "secao": exportacao["secao"],
        "campos": campos,
        "quantidade": exportacao["quantidade"],
        "gerado_em": exportacao["gerado_em"],
        "versao_relatorio": exportacao["versao_relatorio"],
        "sem_scraping": True,
        "executou_motor": False,
        "alterou_decisao": False,
        "dados_sensiveis_exportados": False,
        "conteudo": saida.getvalue(),
        "content_type": "text/csv; charset=utf-8",
    }


def gerar_exportacao(*, formato: str = "json", secao: str = "decisoes", limite: int = 50, incluir_replay: bool = False) -> dict[str, Any]:
    formato_norm = str(formato or "json").lower().strip()
    if formato_norm == "json":
        return gerar_exportacao_json(secao=secao, limite=limite, incluir_replay=incluir_replay)
    if formato_norm == "csv":
        return gerar_exportacao_csv(secao=secao, limite=limite, incluir_replay=incluir_replay)
    return {
        "status": "erro",
        "mensagem": "Formato de exportação inválido.",
        "formatos_validos": ["csv", "json"],
    }
