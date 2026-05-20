"""
api/setup_cvm.py

Endpoints de bootstrap da infraestrutura CVM do FIIA.

Executa via API as mesmas operações do script bootstrap_cvm.py:
  - POST /api/setup/cvm/tabela-mestre  → importa tabela_mestre_fiia_fiis_b3_cvm.csv
  - POST /api/setup/cvm/informes       → baixa informes mensais CVM de um ou mais anos
  - POST /api/setup/cvm/completo       → executa os dois em sequência
  - GET  /api/setup/cvm/status         → informa cobertura atual no banco

Todos os endpoints de escrita exigem API key e rate limit "sensivel".
"""
from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from acesso.rate_limit import dependencia_rate_limit
from acesso.seguranca import verificar_api_key, resposta_erro_segura
from sistema import observabilidade

router = APIRouter(prefix="/api/setup/cvm", tags=["setup-cvm"])

_TABELA_MESTRE_PADRAO = Path(__file__).parent.parent / "tabela_mestre_fiia_fiis_b3_cvm.csv"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _importar_tabela() -> dict[str, Any]:
    from coleta.tabela_mestre_fiis import importar_csv, obter_por_ticker

    if not _TABELA_MESTRE_PADRAO.exists():
        return {
            "status": "ERRO",
            "motivo": f"Arquivo não encontrado: {_TABELA_MESTRE_PADRAO.name}",
        }

    t0 = time.time()
    resumo = importar_csv(_TABELA_MESTRE_PADRAO)
    elapsed = round(time.time() - t0, 1)

    if "erro" in resumo:
        return {"status": "ERRO", "motivo": resumo["erro"], "elapsed_s": elapsed}

    # Verificação rápida
    amostras = ["HGLG11", "KNCR11", "MXRF11"]
    verificacao = {}
    for ticker in amostras:
        item = obter_por_ticker(ticker)
        verificacao[ticker] = item.get("cnpj_fundo") if item else None

    return {
        "status": "OK",
        "registros": resumo.get("registros", 0),
        "ignorados": resumo.get("ignorados", 0),
        "elapsed_s": elapsed,
        "verificacao_amostra": verificacao,
    }


def _coletar_anos(anos: list[int]) -> dict[str, Any]:
    from coleta.cvm_informe_mensal import coletar_ano, ultimo_por_cnpj
    from coleta.tabela_mestre_fiis import obter_por_ticker

    resultados = []
    total = 0

    for ano in sorted(set(anos)):
        t0 = time.time()
        res = coletar_ano(ano)
        elapsed = round(time.time() - t0, 1)
        registros = res.get("registros_processados", 0)
        total += registros

        if "erro" in res:
            resultados.append({"ano": ano, "status": "ERRO", "motivo": res["erro"]})
        else:
            resultados.append({"ano": ano, "status": "OK", "registros": registros, "elapsed_s": elapsed})

    # Verificação patrimonial
    verificacao = {}
    for ticker in ["HGLG11", "KNCR11"]:
        identidade = obter_por_ticker(ticker)
        if identidade and identidade.get("cnpj_fundo"):
            informe = ultimo_por_cnpj(identidade["cnpj_fundo"])
            if informe:
                verificacao[ticker] = {
                    "vp_cota": informe.get("valor_patrimonial_cota"),
                    "competencia": informe.get("competencia"),
                }
            else:
                verificacao[ticker] = {"aviso": "CNPJ resolvido mas sem informe no banco"}
        else:
            verificacao[ticker] = {"aviso": "Sem CNPJ — rode /tabela-mestre primeiro"}

    status_geral = "OK" if all(r["status"] == "OK" for r in resultados) else "PARCIAL"
    return {
        "status": status_geral,
        "anos": resultados,
        "total_registros": total,
        "verificacao_patrimonial": verificacao,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
def status_cvm() -> dict[str, Any]:
    """
    Retorna cobertura atual da infraestrutura CVM no banco.
    Não exige API key — leitura apenas.
    """
    try:
        from banco import db
        from coleta.tabela_mestre_fiis import garantir_tabela

        garantir_tabela()

        # Tabela mestre
        row_tm = db.buscar_um("SELECT COUNT(*) as total FROM fiia_tabela_mestre_fiis")
        total_tabela = row_tm["total"] if row_tm else 0

        row_tm_cnpj = db.buscar_um(
            "SELECT COUNT(*) as total FROM fiia_tabela_mestre_fiis WHERE cnpj_fundo IS NOT NULL AND cnpj_fundo != ''"
        )
        com_cnpj = row_tm_cnpj["total"] if row_tm_cnpj else 0

        # Informes CVM
        row_inf = db.buscar_um(
            "SELECT COUNT(*) as total FROM cvm_informes_mensais_fii"
        )
        total_informes = row_inf["total"] if row_inf else 0

        row_competencias = db.buscar_um(
            "SELECT MIN(competencia) as mais_antiga, MAX(competencia) as mais_recente FROM cvm_informes_mensais_fii"
        )

        mais_antiga = row_competencias["mais_antiga"] if row_competencias else None
        mais_recente = row_competencias["mais_recente"] if row_competencias else None

        tabela_ok = total_tabela > 0
        informes_ok = total_informes > 0

        status = "OK" if (tabela_ok and informes_ok) else (
            "PARCIAL" if (tabela_ok or informes_ok) else "VAZIO"
        )

        return {
            "status": status,
            "tabela_mestre": {
                "tickers": total_tabela,
                "com_cnpj": com_cnpj,
                "arquivo_esperado": _TABELA_MESTRE_PADRAO.name,
                "arquivo_existe": _TABELA_MESTRE_PADRAO.exists(),
            },
            "informes_mensais": {
                "registros": total_informes,
                "competencia_mais_antiga": mais_antiga,
                "competencia_mais_recente": mais_recente,
            },
            "proximo_passo": (
                "Tudo pronto." if status == "OK"
                else "Execute POST /api/setup/cvm/completo para inicializar."
            ),
        }

    except Exception as e:
        observabilidade.registrar_erro("api.setup_cvm.status", e)
        return resposta_erro_segura("Falha ao consultar status CVM.")


@router.post(
    "/tabela-mestre",
    dependencies=[Depends(verificar_api_key), Depends(dependencia_rate_limit("sensivel"))],
)
def importar_tabela_mestre() -> dict[str, Any]:
    """
    Importa tabela_mestre_fiia_fiis_b3_cvm.csv para o banco.
    Popula fiia_tabela_mestre_fiis com ticker → CNPJ fundo/classe.
    """
    try:
        resultado = _importar_tabela()
        observabilidade.registrar_evento(
            "INFO", "api.setup_cvm.tabela_mestre",
            "Importação tabela mestre executada via API",
            contexto=resultado,
        )
        return {"status": "ok", "resultado": resultado}
    except Exception as e:
        observabilidade.registrar_erro("api.setup_cvm.tabela_mestre", e)
        return resposta_erro_segura("Falha ao importar tabela mestre.")


@router.post(
    "/informes",
    dependencies=[Depends(verificar_api_key), Depends(dependencia_rate_limit("sensivel"))],
)
def coletar_informes(anos: str = "") -> dict[str, Any]:
    """
    Baixa e persiste informes mensais CVM.

    Parâmetro `anos`: lista separada por vírgula (ex: `2025,2026`).
    Padrão: ano anterior + ano atual.
    """
    try:
        ano_atual = date.today().year
        if anos.strip():
            lista_anos = [int(a.strip()) for a in anos.split(",") if a.strip().isdigit()]
        else:
            lista_anos = [ano_atual - 1, ano_atual]

        if not lista_anos:
            return {"status": "erro", "motivo": "Nenhum ano válido informado."}

        resultado = _coletar_anos(lista_anos)
        observabilidade.registrar_evento(
            "INFO", "api.setup_cvm.informes",
            "Coleta informes CVM executada via API",
            contexto={"anos": lista_anos, "total": resultado.get("total_registros")},
        )
        return {"status": "ok", "resultado": resultado}
    except Exception as e:
        observabilidade.registrar_erro("api.setup_cvm.informes", e)
        return resposta_erro_segura("Falha ao coletar informes CVM.")


@router.post(
    "/completo",
    dependencies=[Depends(verificar_api_key), Depends(dependencia_rate_limit("sensivel"))],
)
def bootstrap_completo(anos: str = "") -> dict[str, Any]:
    """
    Executa bootstrap completo em sequência:
      1. Importa tabela mestre (ticker → CNPJ)
      2. Coleta informes mensais CVM

    Parâmetro `anos`: separado por vírgula. Padrão: ano anterior + ano atual.
    """
    try:
        ano_atual = date.today().year
        lista_anos = (
            [int(a.strip()) for a in anos.split(",") if a.strip().isdigit()]
            if anos.strip()
            else [ano_atual - 1, ano_atual]
        )

        t0 = time.time()

        res_tabela = _importar_tabela()
        res_cvm = _coletar_anos(lista_anos)

        elapsed = round(time.time() - t0, 1)

        status_geral = (
            "OK"
            if res_tabela.get("status") == "OK" and res_cvm.get("status") == "OK"
            else "PARCIAL"
        )

        observabilidade.registrar_evento(
            "INFO", "api.setup_cvm.completo",
            "Bootstrap CVM completo executado via API",
            contexto={"status": status_geral, "elapsed_s": elapsed},
        )

        return {
            "status": "ok",
            "resultado": {
                "status_geral": status_geral,
                "elapsed_total_s": elapsed,
                "tabela_mestre": res_tabela,
                "informes_cvm": res_cvm,
            },
        }
    except Exception as e:
        observabilidade.registrar_erro("api.setup_cvm.completo", e)
        return resposta_erro_segura("Falha no bootstrap CVM.")
