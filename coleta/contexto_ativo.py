"""
coleta/contexto_ativo.py

Módulo unificado para captação, normalização, validação e preparação dos dados de um ativo.
Garante o princípio de Asset Context e o isolamento do motor de decisão.
"""
from __future__ import annotations

import json
import hashlib
import time
from datetime import datetime, date, timezone
from typing import Any, Optional

from banco import db
from config import settings
from sistema import observabilidade

# Cache em memória para evitar requisições repetidas no mesmo radar loop
_CACHE_CONTEXTO: dict[str, dict[str, Any]] = {}

# Versão atual do contexto para invalidação dinâmica de snapshots legados (Achado 2)
VERSAO_CONTEXTO = "asset-context-v1.1"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _converter_data(valor: Any) -> Optional[date]:
    if not valor:
        return None
    if isinstance(valor, (date, datetime)):
        return valor.date() if isinstance(valor, datetime) else valor
    try:
        # Tenta YYYY-MM-DD
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
    except Exception:
        try:
            # Tenta YYYY-MM
            return datetime.strptime(str(valor)[:7], "%Y-%m").date()
        except Exception:
            return None


def obter_contexto_ativo(ticker: str) -> dict[str, Any]:
    """
    Busca o contexto do ativo em cache do dia.
    Se não existir, executa uma coleta nova completa.
    """
    ticker_norm = ticker.upper().replace(".SA", "").strip()
    hoje = date.today().isoformat()
    cache_key = f"{ticker_norm}_{hoje}"

    if cache_key in _CACHE_CONTEXTO:
        return _CACHE_CONTEXTO[cache_key]

    # Verifica se já temos snapshot no banco hoje
    snapshot_row = db.buscar_um(
        "SELECT payload_json FROM snapshots_indicadores WHERE ticker = ? AND data_snapshot = ? ORDER BY criado_em DESC LIMIT 1",
        (ticker_norm, hoje),
    )
    if snapshot_row and snapshot_row["payload_json"]:
        try:
            contexto = json.loads(snapshot_row["payload_json"])
            # Valida se a versão do snapshot do banco é idêntica à versão atual (Achado 2)
            if contexto.get("contexto_versao") == VERSAO_CONTEXTO:
                _CACHE_CONTEXTO[cache_key] = contexto
                return contexto
        except Exception:
            pass

    # Se não houver em cache/banco hoje, faz coleta nova completa
    return coletar_contexto_ativo(ticker_norm, forcar=True)


def coletar_contexto_ativo(ticker: str, forcar: bool = False) -> dict[str, Any]:
    """
    Executa a resolução completa de dados do ativo seguindo a prioridade de fontes,
    normaliza campos, valida divergências e gera o relatório de confiança.
    """
    ticker_norm = ticker.upper().replace(".SA", "").strip()
    hoje = date.today().isoformat()
    cache_key = f"{ticker_norm}_{hoje}"

    if not forcar:
        # Se não for forçado, tenta obter via obter_contexto_ativo para usar cache
        return obter_contexto_ativo(ticker_norm)

    print(f"[contexto] Iniciando coleta robusta para o ativo {ticker_norm}...")
    agora = _agora_iso()

    # Helper memoizado para evitar chamadas duplicadas à API Fundamentus (Achado 6)
    fund_cache = None
    def obter_fundamentus_memo() -> dict:
        nonlocal fund_cache
        if fund_cache is None:
            try:
                from coleta import api_fundamentus
                fund_cache = api_fundamentus.coletar_fii(ticker_norm) or {}
            except Exception as e:
                print(f"[contexto] Falha ao coletar Fundamentus para {ticker_norm}: {e}")
                fund_cache = {}
        return fund_cache

    # 1. Identidade Canônica
    # Prioridade: Tabela Mestre B3/CVM -> Cadastro Local de FIIs -> Fallback
    cnpj_fundo = None
    cnpj_classe = None
    razao_social = None
    nome_fundo = ticker_norm
    segmento = "INDEFINIDO"
    fonte_identidade = "FALLBACK"

    # Busca tabela mestre
    try:
        from coleta import tabela_mestre_fiis
        identidade = tabela_mestre_fiis.obter_por_ticker(ticker_norm)
        if identidade:
            cnpj_fundo = identidade.get("cnpj_fundo")
            cnpj_classe = identidade.get("cnpj_classe")
            razao_social = identidade.get("razao_social")
            nome_fundo = identidade.get("nome_fundo") or nome_fundo
            fonte_identidade = "TABELA_MESTRE_B3_CVM"
    except Exception as e:
        print(f"[contexto] Erro ao carregar tabela mestre para {ticker_norm}: {e}")

    # Busca tabela fiis local para complementar segmento
    fii_row = db.buscar_um("SELECT segmento, nome, tipo FROM fiis WHERE ticker = ?", (ticker_norm,))
    if fii_row:
        segmento = fii_row["segmento"] or segmento
        nome_fundo = fii_row["nome"] or nome_fundo
        if fonte_identidade == "FALLBACK":
            fonte_identidade = "CADASTRO_LOCAL"

    # 2. Coleta de Preço de Mercado
    # Prioridade: yfinance com timestamp -> Fundamentus -> Banco Histórico
    preco = None
    preco_timestamp = None
    preco_fonte = "AUSENTE"
    preco_moeda = "BRL"
    preco_status = "AUSENTE"

    # yfinance
    try:
        from coleta import api_yfinance
        res_yf = api_yfinance.coletar_preco_atual(ticker_norm)
        if res_yf and res_yf.get("preco") is not None:
            preco = float(res_yf["preco"])
            preco_timestamp = res_yf.get("preco_timestamp") or agora
            preco_fonte = res_yf.get("preco_fonte") or "yfinance"
            preco_moeda = res_yf.get("preco_moeda") or "BRL"
            preco_status = "OK"
    except Exception as e:
        print(f"[contexto] Falha yfinance para {ticker_norm}: {e}")

    # Fallback Fundamentus
    if preco is None:
        try:
            res_fund = obter_fundamentus_memo()
            if res_fund and res_fund.get("preco") is not None:
                preco = float(res_fund["preco"])
                preco_timestamp = agora
                preco_fonte = "Fundamentus"
                preco_status = "OK"
        except Exception as e:
            print(f"[contexto] Falha Fundamentus preço para {ticker_norm}: {e}")

    # Fallback Banco (último válido)
    if preco is None:
        db_preco = db.buscar_um(
            "SELECT preco, preco_timestamp, preco_fonte, preco_moeda FROM indicadores WHERE ticker = ? AND preco IS NOT NULL ORDER BY data DESC LIMIT 1",
            (ticker_norm,),
        )
        if db_preco:
            preco = float(db_preco["preco"])
            preco_timestamp = db_preco["preco_timestamp"] or agora
            preco_fonte = db_preco["preco_fonte"] or "banco_historico"
            preco_moeda = db_preco["preco_moeda"] or "BRL"
            preco_status = "OK"

    # Verifica validade temporal do Preço
    if preco is not None and preco_timestamp:
        try:
            ts_parsed = datetime.fromisoformat(preco_timestamp.replace("Z", "+00:00"))
            idade_horas = (datetime.now(timezone.utc) - ts_parsed).total_seconds() / 3600.0
            if idade_horas > settings.PRECO_MAX_IDADE_HORAS:
                preco_status = "VENCIDO"
        except Exception:
            preco_status = "SUSPEITO"

    # 3. Coleta de Dados Patrimoniais (VPA, PL, P/VP)
    # Prioridade: CVM Informe Mensal -> Fundamentus -> Banco Histórico
    patrimonio_liquido = None
    vpa = None
    pvp = None
    patrimonio_fonte = "AUSENTE"
    patrimonio_status = "AUSENTE"
    competencia_patrimonial = None

    # CVM Informe Mensal
    cvm_resolvido = False
    if cnpj_fundo:
        try:
            from servicos import cvm_fii_service
            res_cvm = cvm_fii_service.calcular_pvp_cvm(ticker_norm, preco)
            if res_cvm and res_cvm.get("valor_patrimonial_cota_cvm") is not None:
                patrimonio_liquido = res_cvm.get("patrimonio_liquido_cvm")
                vpa = res_cvm.get("valor_patrimonial_cota_cvm")
                pvp = res_cvm.get("pvp_cvm")
                patrimonio_fonte = "CVM_INF_MENSAL"
                competencia_patrimonial = res_cvm.get("competencia")
                patrimonio_status = "OK"
                cvm_resolvido = True
        except Exception as e:
            print(f"[contexto] Falha CVM para {ticker_norm}: {e}")

    # Fallback Fundamentus
    fund_pl = None
    fund_vpa = None
    fund_pvp = None
    try:
        res_fund = obter_fundamentus_memo()
        if res_fund:
            fund_pl = res_fund.get("patrimonio_liquido")
            fund_vpa = res_fund.get("vpa")
            fund_pvp = res_fund.get("pvp")

            if not cvm_resolvido and fund_vpa is not None:
                patrimonio_liquido = fund_pl
                vpa = fund_vpa
                pvp = fund_pvp
                patrimonio_fonte = "Fundamentus"
                patrimonio_status = "OK"
    except Exception as e:
        print(f"[contexto] Falha Fundamentus patrimonial para {ticker_norm}: {e}")

    # Fallback Banco
    if vpa is None:
        db_patr = db.buscar_um(
            "SELECT patrimonio_liquido, vpa, pvp, coletado_em FROM indicadores WHERE ticker = ? AND vpa IS NOT NULL ORDER BY data DESC LIMIT 1",
            (ticker_norm,),
        )
        if db_patr:
            patrimonio_liquido = db_patr["patrimonio_liquido"]
            vpa = db_patr["vpa"]
            pvp = db_patr["pvp"]
            patrimonio_fonte = "banco_historico"
            patrimonio_status = "OK"

    # Verifica validade temporal do CVM / Patrimônio
    if patrimonio_status == "OK" and patrimonio_fonte == "CVM_INF_MENSAL" and competencia_patrimonial:
        comp_date = _converter_data(competencia_patrimonial)
        if comp_date:
            dias_idade = (date.today() - comp_date).days
            if dias_idade > (settings.CVM_MAX_IDADE_MESES * 30):
                patrimonio_status = "VENCIDO"

    # Recalcula P/VP se tivermos preco e vpa válidos
    if preco is not None and vpa is not None and vpa > 0:
        pvp = round(preco / vpa, 4)

    # 4. Detecção de Divergências Patrimoniais (CVM vs Fundamentus)
    if cvm_resolvido and fund_vpa is not None and vpa is not None:
        divergencia = abs(vpa - fund_vpa) / max(vpa, fund_vpa, 1.0)
        if divergencia > 0.02:  # Tolerância de 2%
            patrimonio_status = "DIVERGENTE"

    # 5. Coleta de Dividendos & Rendimentos
    # Prioridade: Banco local (FNET/yfinance) -> Fundamentus 12M
    ultimo_dividendo = None
    dy_12m = None
    dy_patrimonial = None
    dy_3m = None
    dy_6m = None
    dividendos_fonte = "AUSENTE"
    dividendos_status = "AUSENTE"
    recorrencia_dividendos_pct = 0.0

    # Carrega do histórico do banco
    divs = db.buscar_todos(
        "SELECT valor, data_pagamento, tipo, fonte FROM dividendos WHERE ticker = ? ORDER BY data_pagamento DESC LIMIT 24",
        (ticker_norm,),
    )
    
    # Se não houver dividendos locais no banco, tenta a coleta preventiva primeiro (yfinance/FNET) (Achado 3 & 4)
    if not divs:
        try:
            print(f"[contexto] Nenhum dividendo no banco para {ticker_norm}. Iniciando coleta preventiva...")
            from coleta.api_yfinance import coletar_historico_dividendos
            coletar_historico_dividendos(ticker_norm)
            # Tenta buscar novamente após a coleta preventiva
            divs = db.buscar_todos(
                "SELECT valor, data_pagamento, tipo, fonte FROM dividendos WHERE ticker = ? ORDER BY data_pagamento DESC LIMIT 24",
                (ticker_norm,),
            )
        except Exception as e:
            print(f"[contexto] Falha na coleta preventiva de dividendos para {ticker_norm}: {e}")

    if divs:
        divs_lista = [dict(d) for d in divs]
        ultimo_dividendo = float(divs_lista[0]["valor"])
        dividendos_fonte = divs_lista[0].get("fonte") or "dividendos_local"
        dividendos_status = "OK"

        # Verifica obsolecência do último pagamento (ex: > 45 dias)
        last_pagto = _converter_data(divs_lista[0]["data_pagamento"])
        if last_pagto:
            dias_sem_pagamento = (date.today() - last_pagto).days
            if dias_sem_pagamento > 45:
                dividendos_status = "VENCIDO"

        # Calcula DY 12M real com base nos pagamentos dos últimos 365 dias
        hoje_dt = date.today()
        soma_12m = 0.0
        soma_6m = 0.0
        soma_3m = 0.0
        soma_recorrente = 0.0
        total_recorrencia_analisada = 0

        for d in divs_lista:
            d_date = _converter_data(d["data_pagamento"])
            if d_date:
                dias_idade = (hoje_dt - d_date).days
                if dias_idade <= 365:
                    soma_12m += float(d["valor"])
                    total_recorrencia_analisada += 1
                    if d.get("tipo", "RECORRENTE") == "RECORRENTE":
                        soma_recorrente += float(d["valor"])
                if dias_idade <= 180:
                    soma_6m += float(d["valor"])
                if dias_idade <= 90:
                    soma_3m += float(d["valor"])

        if total_recorrencia_analisada > 0:
            recorrencia_dividendos_pct = round(soma_recorrente / max(soma_12m, 0.01), 4)

        if preco is not None and preco > 0:
            dy_12m = round(soma_12m / preco, 4)
            # Retornos de dividendos calculados para o período analisado (não anualizados) (Achado 4)
            dy_6m = round(soma_6m / preco, 4)
            dy_3m = round(soma_3m / preco, 4)
        if vpa is not None and vpa > 0:
            dy_patrimonial = round(soma_12m / vpa, 4)
    else:
        # Fallback para tabela de indicadores do banco ou fundamentus (Achado 2)
        ind_div = db.buscar_um(
            "SELECT dy_3m, dy_6m, dy_12m, ultimo_dividendo, dy_patrimonial FROM indicadores WHERE ticker = ? AND dy_12m IS NOT NULL ORDER BY data DESC LIMIT 1",
            (ticker_norm,),
        )
        if ind_div:
            dy_12m = ind_div["dy_12m"]
            dy_6m = ind_div["dy_6m"]
            dy_3m = ind_div["dy_3m"]
            ultimo_dividendo = ind_div["ultimo_dividendo"]
            dy_patrimonial = ind_div["dy_patrimonial"]
            dividendos_fonte = "indicadores_historico"
            dividendos_status = "OK"

    # 6. Coleta de Indicadores Operacionais
    # Vacância, Liquidez, Qtd Imóveis
    liquidez_diaria = 0.0
    vacancia_fisica = 0.0
    qtd_ativos = 0

    ind_op = db.buscar_um(
        "SELECT liquidez_diaria, vacancia_fisica, qtd_ativos, vacancia_financeira FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
        (ticker_norm,),
    )
    if ind_op:
        ind_op_dict = dict(ind_op)
        liquidez_diaria = ind_op_dict.get("liquidez_diaria") or 0.0
        vacancia_fisica = ind_op_dict.get("vacancia_fisica") or 0.0
        qtd_ativos = ind_op_dict.get("qtd_ativos") or 0

    # Tenta obter dados mais novos com Fundamentus
    res_fund = obter_fundamentus_memo()
    if res_fund:
        liquidez_diaria = res_fund.get("liquidez_diaria") or liquidez_diaria
        vacancia_fisica = res_fund.get("vacancia_fisica") or vacancia_fisica
        qtd_ativos = res_fund.get("qtd_ativos") or qtd_ativos

    # 7. Cálculo do Score Consolidado de Confiança (0 a 100)
    score_confianca = 100
    if preco_status == "AUSENTE":
        score_confianca -= 40
    elif preco_status == "VENCIDO":
        score_confianca -= 20
    elif preco_status == "SUSPEITO":
        score_confianca -= 30

    if patrimonio_status == "AUSENTE":
        score_confianca -= 40
    elif patrimonio_status == "VENCIDO":
        score_confianca -= 15
    elif patrimonio_status == "DIVERGENTE":
        score_confianca -= 25

    if dividendos_status == "AUSENTE":
        score_confianca -= 30
    elif dividendos_status == "VENCIDO":
        score_confianca -= 15

    if not liquidez_diaria:
        score_confianca -= 20

    eh_papel = "PAPEL" in segmento.upper() or "RECEB" in segmento.upper()
    if not eh_papel and not vacancia_fisica:
        score_confianca -= 10

    score_confianca = max(0, min(100, score_confianca))

    # Nível consolidado de uso
    nivel_uso = "INSUFICIENTE"
    if score_confianca >= 80:
        nivel_uso = "CONFIAVEL"
    elif score_confianca >= 60:
        nivel_uso = "USAR_COM_CAUTELA"
    elif score_confianca >= 40:
        nivel_uso = "BLOQUEAR_DECISAO_FORTE"

    # 8. Princípio de Fail-Closed (Bloqueio Automático)
    permitir_decisao = True
    campos_ausentes = []
    campos_vencidos = []
    fontes_falharam = []

    # Validações rígidas de consistência
    if preco is None or preco <= 0:
        permitir_decisao = False
        campos_ausentes.append("preco")
        fontes_falharam.extend(["yfinance", "Fundamentus"])
    elif preco_status == "VENCIDO":
        campos_vencidos.append("preco")

    if vpa is None or vpa <= 0:
        permitir_decisao = False
        campos_ausentes.append("vpa")
        fontes_falharam.extend(["CVM", "Fundamentus"])
    elif patrimonio_status == "VENCIDO":
        campos_vencidos.append("vpa")

    if not liquidez_diaria or liquidez_diaria < settings.LIQUIDEZ_MINIMA_DIARIA:
        permitir_decisao = False
        campos_ausentes.append("liquidez")

    if ultimo_dividendo is None or ultimo_dividendo < 0:
        permitir_decisao = False
        campos_ausentes.append("ultimo_dividendo")
        fontes_falharam.append("FNET")

    if score_confianca < settings.CONFIABILIDADE_MINIMA:
        permitir_decisao = False

    # 9. Consolidação do Contexto
    contexto = {
        "contexto_versao": VERSAO_CONTEXTO,
        "ticker": ticker_norm,
        "data": hoje,
        "atualizado_em": agora,
        "cnpj_fundo": cnpj_fundo,
        "cnpj_classe": cnpj_classe,
        "razao_social": razao_social,
        "nome_fundo": nome_fundo,
        "segmento": segmento,
        "fonte_identidade": fonte_identidade,
        "preco": preco,
        "preco_timestamp": preco_timestamp,
        "preco_fonte": preco_fonte,
        "preco_moeda": preco_moeda,
        "preco_status": preco_status,
        "patrimonio_liquido": patrimonio_liquido,
        "vpa": vpa,
        "pvp": pvp,
        "patrimonio_fonte": patrimonio_fonte,
        "patrimonio_status": patrimonio_status,
        "competencia_patrimonial": competencia_patrimonial,
        "ultimo_dividendo": ultimo_dividendo,
        "dy_12m": dy_12m,
        "dy_patrimonial": dy_patrimonial,
        "dividendos_fonte": dividendos_fonte,
        "dividendos_status": dividendos_status,
        "recorrencia_dividendos_pct": recorrencia_dividendos_pct,
        "liquidez_diaria": liquidez_diaria,
        "vacancia_fisica": vacancia_fisica,
        "qtd_ativos": qtd_ativos,
        "score_confianca": score_confianca,
        "nivel_uso_dados": nivel_uso,
        "permitir_decisao": permitir_decisao,
        "campos_ausentes": campos_ausentes,
        "campos_vencidos": campos_vencidos,
        "fontes_falharam": list(set(fontes_falharam)),
    }

    # 10. Persistência de Duas Camadas
    # Camada A: indicadores operacionais normalizados
    dados_indicadores = {
        "ticker": ticker_norm,
        "data": hoje,
        "preco": preco,
        "preco_timestamp": preco_timestamp,
        "preco_fonte": preco_fonte,
        "preco_moeda": preco_moeda,
        "pvp": pvp,
        "liquidez_diaria": liquidez_diaria,
        "ultimo_dividendo": ultimo_dividendo,
        "dy_3m": dy_3m,
        "dy_6m": dy_6m,
        "dy_12m": dy_12m,
        "dy_patrimonial": dy_patrimonial,
        "vacancia_fisica": vacancia_fisica,
        "vacancia_financeira": dict(ind_op).get("vacancia_financeira") if ind_op else None,
        "patrimonio_liquido": patrimonio_liquido,
        "vpa": vpa,
        "qtd_ativos": qtd_ativos,
        "fonte": patrimonio_fonte,
        "confiabilidade": score_confianca,
        "coletado_em": agora,
    }
    db.upsert("indicadores", dados_indicadores)

    # Camada B: snapshot bruto do contexto auditável (Achado 7)
    # Nota: Um ticker pode ter múltiplos snapshots por dia se o payload mudar.
    # O contexto mais recente de um dia específico é recuperado por ORDER BY criado_em DESC.
    payload_str = json.dumps(contexto, ensure_ascii=False)
    hash_obj = hashlib.sha256(payload_str.encode("utf-8"))
    hash_hex = hash_obj.hexdigest()

    db.executar(
        """
        INSERT OR IGNORE INTO snapshots_indicadores (ticker, data_snapshot, origem_snapshot, payload_json, hash_snapshot, criado_em)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ticker_norm, hoje, "AssetContextResolver", payload_str, hash_hex, agora),
    )

    # Armazena em cache memória
    _CACHE_CONTEXTO[cache_key] = contexto

    observabilidade.registrar_evento(
        "INFO",
        "coleta.contexto_ativo",
        "Contexto de ativo construído e auditado",
        ticker=ticker_norm,
        contexto={
            "preco": preco,
            "vpa": vpa,
            "confianca": score_confianca,
            "permitir_decisao": permitir_decisao,
        },
    )

    return contexto
