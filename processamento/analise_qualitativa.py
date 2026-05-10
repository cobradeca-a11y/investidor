"""
processamento/analise_qualitativa.py
Analista Sênior FIIA — integração com Gemini.

Regra central:
    A IA nunca deve compensar ausência de dado fundamentalista.
    Se os campos mínimos obrigatórios estiverem ausentes ou zerados,
    a análise é bloqueada antes de acionar o Gemini.
"""

import json
import time

from google import genai

from config import settings
from coleta.web_search import buscar_noticias
import banco.db as db


# ─────────────────────────────────────────────────────────────────────────────
# Campos mínimos exigidos para liberar análise qualitativa
# ─────────────────────────────────────────────────────────────────────────────

_CAMPOS_OBRIGATORIOS = {
    # campo no banco        : descrição legível
    "pvp":                   "P/VP",
    "dy_12m":                "Dividend Yield 12M",
    "vacancia_fisica":       "Vacância Física",
    "liquidez_diaria":       "Liquidez Diária",
}

_LIQUIDEZ_MINIMA = 1_000.0      # R$ 1.000 — evita fundos com liquidez zero ou residual


def _resposta_bloqueada(campos_faltando: list[str]) -> dict:
    return {
        "score": None,
        "status": "BLOQUEADO_DADOS_INSUFICIENTES",
        "resumo": "Análise bloqueada: dados fundamentalistas insuficientes para acionar a IA.",
        "riscos": [
            f"Campo ausente ou inválido: {c}" for c in campos_faltando
        ] + [
            "Coleta fundamentalista falhou ou retornou dados incompletos.",
            "IA não acionada para evitar conclusão enviesada.",
        ],
    }


def _validar_dados(dados_banco: dict, fii_info: dict) -> list[str]:
    """
    Retorna lista de campos problemáticos.
    Lista vazia = dados suficientes para análise.
    """
    problemas = []

    for campo, descricao in _CAMPOS_OBRIGATORIOS.items():
        valor = dados_banco.get(campo)

        # Ausente ou explicitamente nulo
        if valor is None or valor == "" or valor == "N/A":
            problemas.append(descricao)
            continue

        # Liquidez zero ou abaixo do mínimo
        if campo == "liquidez_diaria":
            try:
                if float(valor) < _LIQUIDEZ_MINIMA:
                    problemas.append(f"{descricao} abaixo do mínimo (R$ {float(valor):,.2f})")
            except (TypeError, ValueError):
                problemas.append(f"{descricao} com valor inválido")

    # Segmento do fundo também é obrigatório
    if not fii_info.get("segmento"):
        problemas.append("Segmento do fundo")

    return problemas


# ─────────────────────────────────────────────────────────────────────────────
# Interface pública
# ─────────────────────────────────────────────────────────────────────────────

def analisar_fundo_ia(ticker: str) -> dict:
    """
    Analista Sênior FIIA: interpreta notícias e indicadores fundamentais.

    Fluxo:
        1. Carrega dados do banco
        2. Valida campos mínimos → bloqueia se insuficientes
        3. Verifica chave Gemini
        4. Busca notícias (Google News RSS / DuckDuckGo)
        5. Aciona Gemini com contexto completo
        6. Retorna JSON estruturado
    """
    ticker = ticker.upper().strip()

    # ── 1. Carrega dados do banco ──────────────────────────────────────────
    dados_banco = db.get_by_ticker("indicadores", ticker) or {}
    fii_info    = db.get_by_ticker("fiis",        ticker) or {}

    # ── 2. Validação de dados mínimos ──────────────────────────────────────
    campos_faltando = _validar_dados(dados_banco, fii_info)
    if campos_faltando:
        print(f"[ia] ❌ {ticker} bloqueado — dados insuficientes: {campos_faltando}")
        return _resposta_bloqueada(campos_faltando)

    # ── 3. Verifica chave Gemini ───────────────────────────────────────────
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY in ("", "SUA_CHAVE_AQUI", "sua_chave_aqui"):
        return {
            "score": None,
            "status": "BLOQUEADO_SEM_CHAVE_API",
            "resumo": "⚠️ Chave Gemini não configurada. Defina GEMINI_API_KEY no arquivo .env.",
            "riscos": ["Chave de API ausente ou inválida"],
        }

    # ── 4. Contexto financeiro (dados confirmados) ─────────────────────────
    contexto_financeiro = f"""
    Indicadores Confirmados de {ticker}:
    - Segmento: {fii_info.get('segmento')}
    - P/VP: {dados_banco.get('pvp')}
    - Dividend Yield (12M): {dados_banco.get('dy_12m')}%
    - Vacância Física: {dados_banco.get('vacancia_fisica')}%
    - Liquidez Diária: R$ {float(dados_banco.get('liquidez_diaria', 0)):,.2f}
    """

    # ── 5. Notícias (falha tolerada — não bloqueia análise) ────────────────
    noticias_brutas = buscar_noticias(ticker)
    contexto_noticias = (
        noticias_brutas
        if noticias_brutas
        else "Nenhuma notícia recente encontrada. Foque exclusivamente nos indicadores."
    )

    # ── 6. Prompt ──────────────────────────────────────────────────────────
    prompt = f"""
    Você é um Analista de Investimentos Sênior especializado em FIIs brasileiros.
    Os dados abaixo foram validados e estão completos. Não invente informações ausentes.

    {contexto_financeiro}

    Notícias e Sentimento do Mercado:
    {contexto_noticias}

    Analise:
    1. A sustentabilidade dos dividendos frente ao segmento.
    2. Se o P/VP indica oportunidade real ou armadilha de valor.
    3. Atribua um Score de 0 a 10 baseado exclusivamente nos dados acima.

    Responda APENAS em JSON puro, sem markdown, sem explicações fora do JSON:
    {{
      "score": int,
      "resumo": "string (máximo 3 parágrafos)",
      "riscos": ["string", "string"]
    }}
    """

    # ── 7. Chama Gemini com retry para 429 ────────────────────────────────
    try:
        client   = genai.Client(api_key=settings.GEMINI_API_KEY)
        model_id = "gemini-2.0-flash"

        print(f"[ia] 🔍 Analista Sênior processando {ticker}...")

        response = None
        for tentativa in range(3):
            try:
                response = client.models.generate_content(model=model_id, contents=prompt)
                break
            except Exception as e:
                if "429" in str(e) and tentativa < 2:
                    print(f"[ia] Quota atingida (429). Aguardando 65s — tentativa {tentativa + 1}/3...")
                    time.sleep(65)
                else:
                    raise

        if response is None:
            raise RuntimeError("Gemini não retornou resposta após 3 tentativas.")

        # ── 8. Parse do JSON ───────────────────────────────────────────────
        texto = response.text
        if "```json" in texto:
            texto = texto.split("```json")[1].split("```")[0]
        elif "```" in texto:
            texto = texto.split("```")[1].split("```")[0]

        data = json.loads(texto.strip())

        # Garante que score veio como número
        if not isinstance(data.get("score"), (int, float)):
            raise ValueError(f"Score inválido retornado pela IA: {data.get('score')}")

        data["status"] = "OK"
        print(f"[ia] ✅ Veredito para {ticker}: score {data['score']}/10")
        return data

    except Exception as e:
        print(f"[ia] ❌ Erro ao acionar Gemini: {e}")
        return {
            "score": None,
            "status": "ERRO_IA",
            "resumo": f"Erro técnico ao acionar o Gemini: {str(e)[:120]}",
            "riscos": ["Falha na comunicação com a IA — tente novamente em instantes"],
        }
