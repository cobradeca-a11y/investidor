"""
processamento/analise_qualitativa.py
Analista Sênior FIIA - integração com Gemini.

Fontes de contexto (por ordem de precisão):
  1. Relatório Gerencial PDF via FNET/B3  ← fonte primária
  2. Notícias Google News RSS / DuckDuckGo ← fallback se PDF falhar
  3. Sem contexto qualitativo             ← análise só pelos indicadores

Regra central:
  A IA nunca deve compensar ausência de dado fundamentalista.
  Se os campos mínimos obrigatórios estiverem ausentes, a análise é bloqueada.
"""

import json
import time

from google import genai

from config import settings
from coleta.web_search import buscar_noticias
from coleta.relatorio_fnet import obter_relatorio
import banco.db as db


# ─────────────────────────────────────────────────────────────────────────────
# Campos mínimos obrigatórios
# ─────────────────────────────────────────────────────────────────────────────

_CAMPOS_OBRIGATORIOS = {
    "pvp":             "P/VP",
    "dy_12m":          "Dividend Yield 12M",
    "vacancia_fisica": "Vacância Física",
    "liquidez_diaria": "Liquidez Diária",
}

_LIQUIDEZ_MINIMA = 1_000.0


def _resposta_bloqueada(campos_faltando: list[str]) -> dict:
    return {
        "score":  None,
        "status": "BLOQUEADO_DADOS_INSUFICIENTES",
        "resumo": "Análise bloqueada: dados fundamentalistas insuficientes para acionar a IA.",
        "riscos": [
            f"Campo ausente ou inválido: {c}" for c in campos_faltando
        ] + [
            "Coleta fundamentalista falhou ou retornou dados incompletos.",
            "IA não acionada para evitar conclusão enviesada.",
        ],
        "fonte_qualitativa": None,
    }


def _validar_dados(dados_banco: dict, fii_info: dict) -> list[str]:
    problemas = []
    segmento = fii_info.get("segmento", "").upper()
    
    for campo, descricao in _CAMPOS_OBRIGATORIOS.items():
        valor = dados_banco.get(campo)
        
        # Vacância é opcional para fundos de Papel/Recebíveis ou Agro/Terra
        if campo == "vacancia_fisica":
            if any(x in segmento for x in ["PAPEL", "RECEBÍVEIS", "AGRO", "TERRA", "OUTROS"]):
                continue
                
        if valor is None or valor == "" or valor == "N/A":
            problemas.append(descricao)
            continue
            
        if campo == "liquidez_diaria":
            try:
                if float(valor) < _LIQUIDEZ_MINIMA:
                    problemas.append(f"{descricao} abaixo do mínimo (R$ {float(valor):,.2f})")
            except (TypeError, ValueError):
                problemas.append(f"{descricao} com valor inválido")

    if not segmento:
        problemas.append("Segmento do fundo")

    return problemas


# ─────────────────────────────────────────────────────────────────────────────
# Interface pública
# ─────────────────────────────────────────────────────────────────────────────

def analisar_fundo_ia(ticker: str) -> dict:
    """
    Analista Sênior FIIA.

    Fluxo:
      1. Carrega dados do banco
      2. Valida campos mínimos → bloqueia se insuficientes
      3. Verifica chave Gemini
      4. Tenta obter Relatório Gerencial (FNET/PDF)  ← primário
      5. Se falhar, busca notícias (Google News / DDG) ← fallback
      6. Monta prompt e aciona Gemini
      7. Retorna JSON estruturado com campo fonte_qualitativa
    """
    ticker = ticker.upper().strip()

    # ── 1. Dados do banco ─────────────────────────────────────────────────
    dados_banco = db.get_by_ticker("indicadores", ticker) or {}
    fii_info    = db.get_by_ticker("fiis",        ticker) or {}

    # ── 2. Validação mínima ───────────────────────────────────────────────
    campos_faltando = _validar_dados(dados_banco, fii_info)
    if campos_faltando:
        print(f"[ia] ERRO {ticker} bloqueado - dados insuficientes: {campos_faltando}")
        return _resposta_bloqueada(campos_faltando)

    # ── 3. Chave Gemini ───────────────────────────────────────────────────
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY in ("", "SUA_CHAVE_AQUI", "sua_chave_aqui"):
        return {
            "score":  None,
            "status": "BLOQUEADO_SEM_CHAVE_API",
            "resumo": "⚠️ Chave Gemini não configurada. Defina GEMINI_API_KEY no arquivo .env.",
            "riscos": ["Chave de API ausente ou inválida"],
            "fonte_qualitativa": None,
        }

    # ── 4. Contexto financeiro (dados confirmados) ────────────────────────
    segmento   = fii_info.get("segmento", "Não informado")
    pvp        = dados_banco.get("pvp")
    dy_12m     = dados_banco.get("dy_12m")
    vacancia   = dados_banco.get("vacancia_fisica")
    liquidez   = dados_banco.get("liquidez_diaria", 0)
    vpa        = dados_banco.get("vpa")
    preco      = dados_banco.get("preco")
    qtd_ativos = dados_banco.get("qtd_ativos")

    contexto_financeiro = f"""
INDICADORES FUNDAMENTALISTAS CONFIRMADOS - {ticker}
────────────────────────────────────────────────────
Segmento       : {segmento}
Preço Atual    : R$ {preco}
VP/Cota (VPA)  : R$ {vpa}
P/VP           : {pvp}  {'← abaixo do patrimonial (desconto)' if pvp and float(pvp) < 1 else '← acima do patrimonial (ágio)'}
DY 12M         : {float(dy_12m)*100:.2f}% a.a.
Vacância Física: {vacancia}%
Liquidez Diária: R$ {float(liquidez):,.0f}
Qtd. Imóveis   : {qtd_ativos or 'Não informado'}
────────────────────────────────────────────────────
"""

    # ── 5a. Tenta relatório gerencial FNET (fonte primária) ───────────────
    texto_relatorio   = obter_relatorio(ticker)
    fonte_qualitativa = None

    if texto_relatorio:
        contexto_qualitativo = f"""
RELATÓRIO GERENCIAL (fonte: FNET/B3 - documento oficial do gestor)
────────────────────────────────────────────────────
{texto_relatorio}
────────────────────────────────────────────────────
"""
        fonte_qualitativa = "relatorio_gerencial_fnet"
        print(f"[ia] DOC {ticker} - usando Relatorio Gerencial como contexto qualitativo.")

    else:
        # ── 5b. Fallback: notícias ─────────────────────────────────────────
        noticias = buscar_noticias(ticker)
        if noticias:
            contexto_qualitativo = f"""
NOTÍCIAS RECENTES (fonte: Google News / DuckDuckGo - fallback)
────────────────────────────────────────────────────
{noticias}
────────────────────────────────────────────────────
ATENÇÃO: Relatório gerencial não obtido. Análise qualitativa baseada em notícias
de portal, menos precisas que o documento oficial. Seja conservador nos riscos.
────────────────────────────────────────────────────
"""
            fonte_qualitativa = "noticias_portal"
            print(f"[ia] INFO {ticker} - FNET indisponivel, usando noticias como fallback.")
        else:
            contexto_qualitativo = """
CONTEXTO QUALITATIVO: Nenhuma fonte disponível.
Analise exclusivamente pelos indicadores fundamentalistas acima.
Não faça suposições sobre gestão, portfólio ou mercado sem dados concretos.
"""
            fonte_qualitativa = "apenas_indicadores"
            print(f"[ia] AVISO {ticker} - sem contexto qualitativo. Analise pelos indicadores apenas.")

    # ── 6. Prompt ─────────────────────────────────────────────────────────
    prompt = f"""
Você é um Analista de Investimentos Sênior especializado em Fundos Imobiliários brasileiros (FIIs).
Sua análise deve ser objetiva, baseada EXCLUSIVAMENTE nos dados fornecidos abaixo.
Não invente informações. Não use conhecimento genérico sobre o fundo além do que está no contexto.

{contexto_financeiro}

{contexto_qualitativo}

INSTRUÇÕES DE ANÁLISE:
1. Avalie a sustentabilidade dos dividendos considerando segmento, DY e vacância.
2. Interprete o P/VP: desconto é oportunidade real ou sinal de problema estrutural?
3. Se o relatório gerencial estiver disponível, extraia obrigatoriamente:
   - Tom do gestor (otimista, neutro ou defensivo)
   - Eventos relevantes citados (vencimento de contratos, obras, novos inquilinos, inadimplência)
   - Alertas de risco mencionados pelo próprio gestor
4. Atribua Score de 0 a 10 baseado EXCLUSIVAMENTE nos dados acima:
   - 8-10: oportunidade clara - margem de segurança e fundamentos sólidos
   - 5-7:  fundo razoável com riscos identificados e gerenciáveis
   - 3-4:  fundo com problemas que exigem cautela antes de aportar
   - 0-2:  evitar - fundamentos comprometidos ou riscos críticos não resolvidos

Responda APENAS em JSON puro, sem markdown, sem texto fora do JSON:
{{
  "score": <inteiro 0-10>,
  "resumo": "<análise objetiva em até 3 parágrafos>",
  "riscos": ["<risco específico 1>", "<risco específico 2>", "<risco específico 3>"],
  "tom_gestor": "<otimista|neutro|defensivo|nao_disponivel>",
  "eventos_relevantes": ["<evento 1>", "<evento 2>"]
}}
"""

    # ── 7. Chama Gemini com retry para 429 ────────────────────────────────
    try:
        client   = genai.Client(api_key=settings.GEMINI_API_KEY)
        model_id = "gemini-2.5-flash"

        print(f"[ia] Analisando {ticker}...")

        response = None
        for tentativa in range(3):
            try:
                response = client.models.generate_content(model=model_id, contents=prompt)
                break
            except Exception as e:
                if "429" in str(e) and tentativa < 2:
                    print(f"[ia] Quota atingida (429). Aguardando 65s - tentativa {tentativa + 1}/3...")
                    time.sleep(65)
                else:
                    raise

        if response is None:
            raise RuntimeError("Gemini não retornou resposta após 3 tentativas.")

        # ── 8. Parse do JSON Robusto ─────────────────────────────────────────
        texto = response.text
        
        # Extrai apenas o bloco JSON se houver markdown
        if "```json" in texto:
            texto = texto.split("```json")[1].split("```")[0]
        elif "```" in texto:
            texto = texto.split("```")[1].split("```")[0]

        # Limpeza de caracteres que costumam quebrar o json.loads
        texto_limpo = texto.strip()
        # Remove possíveis quebras de linha dentro de strings ou caracteres de controle
        texto_limpo = texto_limpo.replace('\n', ' ').replace('\r', '')
        
        try:
            data = json.loads(texto_limpo)
        except json.JSONDecodeError:
            # Segunda tentativa: tenta apenas o que estiver entre chaves { }
            import re
            match = re.search(r'\{.*\}', texto, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise

        if not isinstance(data.get("score"), (int, float, type(None))):
            # Se vier nulo ou algo estranho, tenta converter
            try:
                data["score"] = int(data.get("score"))
            except:
                data["score"] = None

        data["status"]            = "OK"
        data["fonte_qualitativa"] = fonte_qualitativa

        print(
            f"[ia] OK {ticker} - Score: {data['score']}/10 | "
            f"Fonte: {fonte_qualitativa} | "
            f"Tom: {data.get('tom_gestor', 'N/A')}"
        )
        return data

    except Exception as e:
        print(f"[ia] ERRO ao acionar Gemini: {e}")
        return {
            "score":  None,
            "status": "ERRO_IA",
            "resumo": f"Erro técnico ao acionar o Gemini: {str(e)[:120]}",
            "riscos": ["Falha na comunicação com a IA — tente novamente em instantes"],
            "fonte_qualitativa": fonte_qualitativa,
        }
